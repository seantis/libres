from __future__ import annotations

import sedate

from datetime import datetime, timedelta, time
from itertools import groupby
from sqlalchemy import types
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.schema import Column
from sqlalchemy.schema import Index
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.orm import object_session
from sqlalchemy.orm.util import has_identity

from libres.db.models import ORMBase
from libres.db.models.types import UUID, UTCDateTime, JSON
from libres.db.models.other import OtherModels
from libres.db.models.timestamp import TimestampMixin
from libres.modules import utils
from libres.modules.rasterizer import (
    rasterize_start,
    rasterize_span,
    rasterize_end,
    iterate_span,
    MIN_RASTER
)


from typing import Any
from typing import TypeVar
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterator
    from sedate.types import TzInfoOrName
    from sqlalchemy.orm import Query
    from typing import NamedTuple
    from typing_extensions import Self

    from libres.db.models import ReservedSlot
    from libres.modules.rasterizer import Raster

    _OptDT1 = TypeVar('_OptDT1', 'datetime | None', datetime, None)
    _OptDT2 = TypeVar('_OptDT2', 'datetime | None', datetime, None)

    class _ReservationIdRow(NamedTuple):
        id: int


class Allocation(TimestampMixin, ORMBase, OtherModels):
    """Describes a timespan within which one or many timeslots can be
    reserved.

    There's an important concept to understand before working with allocations.
    The resource uuid of an alloction is not always pointing to the actual
    resource.

    A resource may in fact be a real resource, or an imaginary resource with
    a uuid derived from the real resource. This is a somewhat historical
    artifact.

    If you need to know which allocations belong to a real resource, the
    mirror_of field is what's relevant. The originally created allocation
    with the real_resource is also called the master-allocation and it is
    the one allocation with mirror_of and resource being equal.

    When in doubt look at the managed_* functions of the
    :class:`.scheduler.Scheduler` class.

    """

    __tablename__ = 'allocations'

    #: the id of the allocation, autoincremented
    id: Column[int] = Column(
        types.Integer(),
        primary_key=True,
        autoincrement=True
    )

    #: the resource uuid of the allocation, may not be an actual resource
    #: see :class:`.models.Allocation` for more information
    resource: Column[uuid.UUID] = Column(UUID(), nullable=False)

    #: the polymorphic type of the allocation
    type: Column[str | None] = Column(types.Text(), nullable=True)

    #: resource of which this allocation is a mirror. If the mirror_of
    #: attribute equals the resource, this is a real resource
    #: see :class:`.models.Allocation` for more information
    mirror_of: Column[uuid.UUID] = Column(UUID(), nullable=False)

    #: Group uuid to which this allocation belongs to. Every allocation has a
    #: group but some allocations may be the only one in their group.
    group: Column[uuid.UUID] = Column(UUID(), nullable=False)

    #: Number of times this allocation may be reserved
    # FIXME: Why is this not nullable=False? For now we pretend that it is
    quota: Column[int] = Column(types.Integer(), default=1)

    #: Maximum number of times this allocation may be reserved with one
    #: single reservation.
    quota_limit: Column[int] = Column(
        types.Integer(),
        default=0,
        nullable=False
    )

    #: Partly available allocations may be reserved partially. How They may
    #: be partitioned is defined by the allocation's raster.
    partly_available: Column[bool] = Column(types.Boolean(), default=False)

    #: True if reservations for this allocation must be approved manually.
    approve_manually: Column[bool] = Column(types.Boolean(), default=False)

    #: The timezone this allocation resides in.
    # FIXME: Why is this not nullable=False? A lot of properties rely on this!
    timezone: Column[str | None] = Column(types.String())

    #: Custom data reserved for the user
    data: Column[dict[str, Any] | None] = Column(
        JSON(),
        nullable=True
    )

    _start: Column[datetime] = Column(
        UTCDateTime(timezone=False),
        nullable=False
    )
    _end: Column[datetime] = Column(
        UTCDateTime(timezone=False),
        nullable=False
    )
    _raster: Column[Raster] = Column(
        types.Integer(),  # type:ignore[arg-type]
        nullable=False
    )

    if TYPE_CHECKING:
        # forward declare backref
        reserved_slots: list[ReservedSlot]

    __table_args__ = (
        Index('mirror_resource_ix', 'mirror_of', 'resource'),
        UniqueConstraint('resource', '_start', name='resource_start_ix')
    )

    __mapper_args__ = {
        'polymorphic_identity': None,
        'polymorphic_on': type
    }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Allocation):
            return False
        return self.resource == other.resource and self._start == other._start

    def __hash__(self) -> int:
        return id(self)

    def copy(self) -> Self:
        """ Creates a new copy of this allocation. """
        allocation = self.__class__()
        allocation.resource = self.resource
        allocation.mirror_of = self.mirror_of
        allocation.group = self.group
        allocation.quota = self.quota
        allocation.partly_available = self.partly_available
        allocation.approve_manually = self.approve_manually
        allocation.timezone = self.timezone
        allocation.data = self.data
        allocation._start = self._start
        allocation._end = self._end
        allocation._raster = self._raster
        return allocation

    def get_start(self) -> datetime:
        return self._start

    def set_start(self, start: datetime) -> None:
        if not start.tzinfo:
            assert self.timezone
            start = sedate.replace_timezone(start, self.timezone)

        if self.raster is not None:
            self._start = rasterize_start(start, self.raster)
        else:
            self._start = rasterize_start(start, MIN_RASTER)  # type:ignore

    #: The start of this allocation. Must be timezone aware.
    #: This date is rastered by the allocation's raster.
    if TYPE_CHECKING:
        # NOTE: type checkers perform some special sauce for property
        #       so the non-decorator style isn't well supported
        @property
        def start(self) -> datetime: ...
        @start.setter
        def start(self, value: datetime) -> None: ...
    else:
        start = property(get_start, set_start)

    def get_end(self) -> datetime:
        return self._end

    def set_end(self, end: datetime) -> None:
        if not end.tzinfo:
            assert self.timezone
            end = sedate.replace_timezone(end, self.timezone)

        if self.raster is not None:
            self._end = rasterize_end(end, self.raster)
        else:
            self._end = rasterize_end(end, MIN_RASTER)  # type:ignore

    #: The end of this allocation. Must be timezone aware.
    #: This date is rastered by the allocation's raster.
    #: The end date is stored with an offset of minues one microsecond
    #: to avoid overlaps with other allocations.
    #: That is to say an allocation that ends at 15:00 really ends at
    #: 14:59:59.999999
    if TYPE_CHECKING:
        # NOTE: type checkers perform some special sauce for property
        #       so the non-decorator style isn't well supported
        @property
        def end(self) -> datetime: ...
        @end.setter
        def end(self, value: datetime) -> None: ...
    else:
        end = property(get_end, set_end)

    def get_raster(self) -> Raster:
        return self._raster

    def set_raster(self, raster: Raster) -> None:
        # the raster can only be set once!
        assert not self._raster
        self._raster = raster  # type:ignore[unreachable]

        # re-rasterize start/end - during initialization it's possible for
        # them not to be setup correctly because that's done using
        # kwargs which has a random order. So it might set start, end, raster
        # in this order one time, then raster, start, end another time.
        #
        # this should of course only happen once - hence the assertion above
        if self._start:
            self._start = rasterize_start(self._start, self.raster)

        if self._end:
            self._end = rasterize_end(self._end, self.raster)

    if TYPE_CHECKING:
        # NOTE: type checkers perform some special sauce for property
        #       so the non-decorator style isn't well supported
        @property
        def raster(self) -> Raster: ...
        @raster.setter
        def raster(self, value: Raster) -> None: ...
    else:
        raster = property(get_raster, set_raster)

    def display_start(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:
        """Returns the start in either the timezone given or the timezone
        on the allocation."""
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone

        return sedate.to_timezone(self.start, timezone)

    def display_end(
        self,
        timezone: TzInfoOrName | None = None
    ) -> datetime:
        """Returns the end plus one microsecond in either the timezone given
        or the timezone on the allocation.

        """
        if timezone is None:
            assert self.timezone is not None
            timezone = self.timezone

        end = self.end + timedelta(microseconds=1)
        return sedate.to_timezone(end, timezone)

    def _prepare_range(
        self,
        start: _OptDT1,
        end: _OptDT2
    ) -> tuple[_OptDT1, _OptDT2]:

        if start:
            assert self.timezone is not None
            start = sedate.standardize_date(start, self.timezone)
        if end:
            assert self.timezone is not None
            end = sedate.standardize_date(end, self.timezone)

        return start, end

    @property
    def whole_day(self) -> bool:
        """True if the allocation is a whole-day allocation.

        A whole-day allocation is not really special. It's just an allocation
        which starts at 0:00 and ends at 24:00 (or 23:59:59'999). Relative
        to its timezone.

        As such it can actually also span multiple days, only hours and minutes
        count.

        The use of this is to display allocations spanning days differently.
        """

        s, e = self.display_start(), self.display_end()
        assert s != e  # this can never be, except when caused by cosmic rays
        assert self.timezone is not None
        return sedate.is_whole_day(s, e, self.timezone)

    def overlaps(self, start: datetime, end: datetime) -> bool:
        """ Returns true if the allocation overlaps with the given dates. """

        start, end = self._prepare_range(start, end)
        start, end = rasterize_span(start, end, self.raster)

        return sedate.overlaps(start, end, self.start, self.end)

    def contains(self, start: datetime, end: datetime) -> bool:
        """ Returns true if the the allocation contains the given dates. """

        start, end = self._prepare_range(start, end)
        start, end = rasterize_span(start, end, self.raster)

        return self.start <= start and end <= self.end

    def free_slots(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> list[tuple[datetime, datetime]]:
        """ Returns the slots which are not yet reserved. """
        reserved = {slot.start for slot in self.reserved_slots}

        return [
            (slot_start, slot_end)
            for slot_start, slot_end in self.all_slots(start, end)
            if slot_start not in reserved
        ]

    def align_dates(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> tuple[datetime, datetime]:
        """ Aligns the given dates to the start and end date of the allocation.

        """

        start, end = self._prepare_range(start, end)

        start = start or self.start
        start = start < self.start and self.start or start

        end = end or self.end
        end = end > self.end and self.end or end

        return start, end

    def all_slots(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> Iterator[tuple[datetime, datetime]]:
        """ Returns the slots which exist with this timespan. Reserved or free.

        """
        start, end = self.align_dates(start, end)

        if self.partly_available:
            yield from iterate_span(start, end, self.raster)
        else:
            yield self.start, self.end

    def count_slots(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> int:
        """ Returns the number of slots which exist with this timespan.
        Reserved or free.

        """
        if not self.partly_available:
            return 1

        start, end = self.align_dates(start, end)
        seconds = (end + timedelta(microseconds=1) - start).total_seconds()

        return int(seconds) // (self.raster * 60)

    def is_available(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> bool:
        """ Returns true if the given daterange is completely available. """

        if not (start and end):
            start, end = self.start, self.end

        assert self.overlaps(start, end)
        reserved = {slot.start for slot in self.reserved_slots}

        for slot_start, _ in self.all_slots(start, end):
            if slot_start in reserved:
                return False

        return True

    def limit_timespan(
        self,
        start: time,
        end: time,
        timezone: TzInfoOrName | None = None,
        is_dst: bool = False,
        raise_non_existent: bool = False,
        raise_ambiguous: bool = False
    ) -> tuple[datetime, datetime]:
        """ Takes the given timespan and moves the start/end date to
        the closest reservable slot. So if 10:00 - 11:00 is requested it will

        - on a partly available allocation return 10:00 - 11:00 if the raster
          allows for that

        - on a non-partly available allocation return the start/end date of
          the allocation itself.

        The resulting times are combined with the allocations start/end date
        to form a datetime. (time in, datetime out -> maybe not the best idea)

        For timezones with DST you may use ``is_dst``, ``raise_non_existent``
        and ``raise_ambiguous`` to deal with DST <-> ST transitions with the
        way you choose. It is recommended to at least raise
        ``pytz.NonExistentTimeError`` to avoid timespans that run backwards.

        """
        timezone = timezone or self.timezone

        if self.partly_available:
            assert isinstance(start, time)
            assert isinstance(end, time)

            s, e = sedate.get_date_range(
                self.display_start(timezone),
                start,
                end,
                is_dst=is_dst,
                raise_non_existent=raise_non_existent,
                raise_ambiguous=raise_ambiguous
            )

            if self.display_end(timezone) < e:
                e = self.display_end()

            if self.display_start(timezone) > s:
                s = self.display_start()

            s, e = rasterize_span(s, e, self.raster)

            return s, e + timedelta(microseconds=1)
        else:
            return self.display_start(timezone), self.display_end(timezone)

    @property
    def pending_reservations(self) -> Query[_ReservationIdRow]:
        """ Returns the pending reservations query for this allocation.
        As the pending reservations target the group and not a specific
        allocation this function returns the same value for masters and
        mirrors.

        """
        assert not self.is_transient, (
            "Don't call if the allocation does not yet exist"
        )

        Reservation = self.models.Reservation  # noqa: N806
        query: Query[_ReservationIdRow]
        query = object_session(self).query(Reservation.id)
        query = query.filter(Reservation.target == self.group)
        query = query.filter(Reservation.status == 'pending')

        return query

    @property
    def waitinglist_length(self) -> int:
        return self.pending_reservations.count()

    @property
    def availability(self) -> float:
        """Returns the availability in percent."""

        total = self.count_slots()
        used = len(self.reserved_slots)

        if total == used:
            return 0.0

        if used == 0:
            return 100.0

        return 100.0 - (float(used) / float(total) * 100.0)

    @property
    def normalized_availability(self) -> float:
        """Most of the time this will be the same value as
        ``availability``.

        For timezones with daylight savings it will treat the transition
        days with 23 and 25 hours respectively like a 24 hour day by either
        adding an imaginary unavailable hour or skipping the first ambiguous
        hour, that way the percentage will visually match what we return from
        from ``:func:availability_partitions``.

        """

        # partly available allocations don't need to be normalized
        if not self.partly_available:
            return self.availability

        start = self.display_start()
        end = self.display_end()

        # nothing to normalize if there was no transition
        if start.tzname() == end.tzname():
            return self.availability

        real_delta = (end - start)
        naive_delta = (end.replace(tzinfo=None) - start.replace(tzinfo=None))

        # the normalized total slots correspond to the naive delta
        total = naive_delta.total_seconds() // (self.raster * 60)
        if real_delta > naive_delta:
            # this is the most complicated case since we need to
            # reduce the set of reserved slots by the hour we skipped
            ambiguous_start = start.replace(
                hour=2, minute=0, second=0, microsecond=0)
            ambiguous_end = ambiguous_start.replace(hour=3)
            used = sum(
                1 for r in self.reserved_slots
                if not ambiguous_start <= r.start < ambiguous_end
            )
        else:
            used = len(self.reserved_slots)
            # add one hour's worth of reserved slots
            used += 60 // self.raster

        if used == 0:
            return 100.0

        if total == used:
            return 0.0

        return 100.0 - (float(used) / float(total) * 100.0)

    @property
    def in_group(self) -> int:
        """True if the event is in any group."""

        query = object_session(self).query(Allocation.id)
        query = query.filter(Allocation.resource == self.resource)
        query = query.filter(Allocation.group == self.group)
        query = query.limit(2)

        return len(query.all()) > 1

    @property
    def quota_left(self) -> int:
        # this can be done quickly if this is a master with a quota of 1
        if self.is_master and self.quota == 1:
            return 1 if self.is_available() else 0

        # if not we need to go through the mirrors
        free_quota = 0

        for mirror in self.siblings():
            if mirror.is_available():
                free_quota += 1

        return free_quota

    def find_spot(
        self,
        start: datetime,
        end: datetime
    ) -> Self | None:
        """ Returns the first free allocation spot amongst the master and the
        mirrors. Honors the quota set on the master and will only try the
        master if the quota is set to 1.

        If no spot can be found, None is returned.

        """
        master = self.get_master()
        if master.is_available(start, end):
            return master

        if master.quota == 1:
            return None

        tries = master.quota - 1

        for mirror in (m for m in self.siblings() if not m.is_master):
            if mirror.is_available(start, end):
                return mirror

            if tries >= 1:
                tries -= 1
            else:
                return None
        return None

    @property
    def is_separate(self) -> bool:
        """True if available separately (as opposed to available only as
        part of a group)."""
        if self.partly_available:
            return True

        if self.in_group:
            return False

        return True

    def normalized_slots(self) -> Iterator[
        tuple[datetime, datetime] | tuple[None, None]
    ]:
        """Most of the times this will return the same thing as all_slots
        however for DST timezones it will ensure the transitions days with
        23 and 25 hours respectively still return 24 hours worth of slots.
        This is achieved by inserting imaginary slots for the non-existent
        hour or removing an hours worth of the ambiguous slots (skipping DST)

        The non-existent time slots will all be a tuple of ``None, None``

        Since frontends usually won't display the 23/25 hours days differently
        users usually cannot pick between the two ambiguous times anyways and
        the non-existent hour cannot be reserved either way.

        For non-partly available allocations it will always return a single
        slot for the entire duration, just the same as ``:func:all_slots``
        """
        if not self.partly_available:
            yield from self.all_slots()
            return

        start = self.display_start()
        end = self.display_end()

        # we don't need to normalize
        if start.tzname() == end.tzname():
            yield from self.all_slots()
            return

        naive_start = start.replace(tzinfo=None)
        naive_end = end.replace(tzinfo=None)
        real_delta = (end - start)
        display_delta = (naive_end - naive_start)

        # the number of slots to skip / insert
        num_slots = 60 // self.raster
        if display_delta < real_delta:
            # 25 hour day, we need to skip the ambiguous hour
            ambiguous_start = start.replace(
                hour=2, minute=0, second=0, microsecond=0)

            skipped = 0
            for s, e in self.all_slots():
                # skip num_slots slots from the first start thats
                # on or after the ambiguous start time
                if skipped < num_slots and s >= ambiguous_start:
                    skipped += 1
                    continue

                yield s, e

        else:
            # 23 hour day, so we need to insert an imaginary hour
            imaginary_start = start.replace(
                hour=2, minute=0, second=0, microsecond=0)
            for s, e in self.all_slots():
                if s == imaginary_start:
                    for _ in range(num_slots):
                        # insert the imaginary slots
                        yield None, None
                yield s, e

    def availability_partitions(
        self,
        normalize_dst: bool = True
    ) -> list[tuple[float, bool]]:
        """Partitions the space between start and end into blocks of either
        free or reserved time. Each block has a percentage representing the
        space the block occupies compared to the size of the whole allocation.

        The blocks are ordered from start to end. Each block is an item with
        two values. The first being the percentage, the second being true if
        the block is reserved.

        So given an allocation that goes from 8 to 9 and a reservation that
        goes from 8:15 until 8:30 we get the following blocks::

            [
                (25%, False),
                (25%, True),
                (50%, False)
            ]

        This is useful to divide an allocation block into different divs on the
        frontend, indicating to the user which parts of an allocation are
        reserved.

        Since usually frontends won't display days with a DST transition in a
        different way, by default this function will normalize the 23/25 hour
        days to a 24 hour day.

        If you wish to instead get the "real" partitions for the 23/25 hour day
        you may pass ``normalize_dst=False``

        """

        if normalize_dst and self.partly_available:
            if not self.reserved_slots:
                # we potentially duplicate some of the work of normalized_slots
                # so we can early out in the most common case
                start = self.display_start()
                end = self.display_end()
                if start.tzname() == end.tzname():
                    return [(100.0, False)]
            slots_iter = self.normalized_slots()

        elif not self.reserved_slots:
            return [(100.0, False)]

        else:
            slots_iter = self.all_slots()

        reserved = {r.start for r in self.reserved_slots}
        slots = tuple(s[0] for s in slots_iter)

        # Get the percentage one slot represents
        step = 100.0 / float(len(slots))

        # Create an entry for each slot with either True or False
        pieces = tuple(s is None or s in reserved for s in slots)

        # Group by the true/false values in the pieces and sum up the
        # percentage
        partitions = []
        total = 0.0

        for flag, group in groupby(pieces, key=lambda p: p):
            percentage = sum(1 for item in group) * step
            partitions.append((percentage, flag))
            total += percentage

        # Make sure to get rid of floating point rounding errors
        diff = 100.0 - total
        if partitions:
            percentage, flag = partitions[-1]
            partitions[-1] = (percentage - diff, flag)

        return partitions

    @property
    def is_transient(self) -> bool:
        """True if the allocation does not exist in the database, and is not
        about to be written to the database. If an allocation is transient it
        means that the given instance only exists in memory.

        See:
        http://www.sqlalchemy.org/docs/orm/session.html
        #quickie-intro-to-object-states
        http://stackoverflow.com/questions/3885601/
        sqlalchemy-get-object-instance-state

        """

        return object_session(self) is None and not has_identity(self)

    @hybrid_property
    def is_master(self) -> bool:
        """True if the allocation is a master allocation."""

        return self.resource == self.mirror_of

    def get_master(self) -> Self:
        if self.is_master:
            return self
        else:
            # FIXME: This should either query `self.__class__` or
            #        we need to return `Allocation` rather than `Self`
            query: Query[Self] = object_session(self).query(Allocation)
            query = query.filter(Allocation._start == self._start)
            query = query.filter(Allocation.resource == self.mirror_of)

            return query.one()

    def siblings(self, imaginary: bool = True) -> list[Self]:
        """Returns the master/mirrors group this allocation is part of.

        If 'imaginary' is true, inexistant mirrors are created on the fly.
        those mirrors are transient (see self.is_transient)

        """

        # this function should always have itself in the result
        if not imaginary and self.is_transient:
            raise AssertionError(
                "the resulting list wouldn't contain this allocation"
            )

        if self.quota == 1:
            assert self.is_master
            return [self]

        # FIXME: This should either query `self.__class__` or
        #        we need to return `Allocation` rather than `Self`
        query: Query[Self] = object_session(self).query(Allocation)
        query = query.filter(Allocation.mirror_of == self.mirror_of)
        query = query.filter(Allocation._start == self._start)

        existing = {e.resource: e for e in query}

        master = self.is_master and self or existing[self.mirror_of]
        existing[master.resource] = master

        uids = utils.generate_uuids(master.resource, master.quota)
        imaginary_len = imaginary and (master.quota - len(existing)) or 0

        siblings = [master]
        for uid in uids:
            if uid in existing:
                siblings.append(existing[uid])
            elif imaginary_len > 0:
                allocation = master.copy()
                allocation.resource = uid
                siblings.append(allocation)

                imaginary_len -= 1

        return siblings
