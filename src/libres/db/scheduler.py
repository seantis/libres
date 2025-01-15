from __future__ import annotations

import sedate

from datetime import datetime, time, timedelta
from operator import attrgetter
from sqlalchemy import func
from sqlalchemy.orm import exc
from sqlalchemy.sql import and_, not_
from uuid import uuid4 as new_uuid, UUID

from libres.context.core import ContextServicesMixin
from libres.db.models import ORMBase, Allocation, ReservedSlot, Reservation
from libres.db.queries import Queries
from libres.modules import errors
from libres.modules import events
from libres.modules import rasterizer
from libres.modules import utils


from typing import overload
from typing import Any
from typing import Literal
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterable
    from collections.abc import Iterator
    from sedate.types import DateLike
    from sqlalchemy.orm import Query
    from typing_extensions import NotRequired, Self, TypeAlias, TypedDict

    from libres.context.core import Context
    from libres.modules.rasterizer import Raster

    _dtrange: TypeAlias = tuple[datetime, datetime]  # noqa: PYI042

    class _ReserveArgs1(TypedDict):
        email: str
        dates: _dtrange | Collection[_dtrange]
        data: NotRequired[Any | None]
        session_id: NotRequired[UUID | None]
        quota: NotRequired[int]
        single_token_per_session: NotRequired[bool]

    class _ReserveArgs2(TypedDict):
        email: str
        group: UUID
        data: NotRequired[Any | None]
        session_id: NotRequired[UUID | None]
        quota: NotRequired[int]
        single_token_per_session: NotRequired[bool]

    _ReserveArgs: TypeAlias = '_ReserveArgs1 | _ReserveArgs2'


missing = object()

Day: TypeAlias = Literal['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su']
DayNumber: TypeAlias = Literal[0, 1, 2, 3, 4, 5, 6]
DAYS_MAP: dict[Day, DayNumber] = {
    'mo': 0,
    'tu': 1,
    'we': 2,
    'th': 3,
    'fr': 4,
    'sa': 5,
    'su': 6
}


class Scheduler(ContextServicesMixin):
    """ The Scheduler is responsible for talking to the backend of the given
    context to create reservations. It is the main part of the API.
    """

    def __init__(
        self,
        context: Context,
        name: str,
        # FIXME: Not quite sure why we don't allow a PyTzInfo
        timezone: str,
        allocation_cls: type[Allocation] = Allocation,
        reservation_cls: type[Reservation] = Reservation
    ):
        """ Initializeds a new Scheduler instance.

        :context:
            The :class:`libres.context.core.Context` this scheduler should
            operate on. Acquire a context by using
            :func:`libres.context.registry.Registry.register_context`.

        :name:
            The name of the Scheduler. The context name and name of the
            scheduler are used to generate the resource uuid in the database.
            To access the data you generated with a scheduler use the same
            context name and scheduler name together.

        :timezone:
            A single scheduler always operates on the same timezone. This is
            used to determine what a whole day means for example (given that
            a whole day starts at 0:00 and ends at 23:59:59).

            Dates passed to the scheduler that are not timezone-aware are
            assumed to be of this timezone!

            This timezone cannot change after allocations have been created!
            If it does, a migration has to be written (as of yet no such
            migration exists).
        """

        assert isinstance(timezone, str)

        self.context = context
        self.queries = Queries(context)

        self.name = name
        self.timezone = timezone

        self.allocation_cls = allocation_cls
        self.reservation_cls = reservation_cls

    def clone(self) -> Self:
        """ Clones the scheduler. The result will be a new scheduler using the
        same context, name, settings and attributes.

        """

        return self.__class__(
            self.context,
            self.name,
            self.timezone,
            self.allocation_cls,
            self.reservation_cls
        )

    @property
    def resource(self) -> UUID:
        """ The resource that belongs to this scheduler. The resource is
        a uuid created from the name and context of this scheduler, based
        on the namespace uuid defined in :ref:`settings.uuid_namespace`

        """
        return self.generate_uuid(self.name)

    def setup_database(self) -> None:
        """ Creates the tables and indices required for libres. This needs
        to be called once per database. Multiple invocations won't hurt but
        they are unnecessary.

        """
        ORMBase.metadata.create_all(self.session.bind)

    def _prepare_dates(
        self,
        dates: utils._NestedIterable[datetime]
    ) -> list[tuple[datetime, datetime]]:
        return [
            (
                sedate.standardize_date(s, self.timezone),
                sedate.standardize_date(e, self.timezone)
            ) for s, e in utils.pairs(dates)
        ]

    def _prepare_range(
        self,
        start: datetime,
        end: datetime
    ) -> tuple[datetime, datetime]:
        return (
            sedate.standardize_date(start, self.timezone),
            sedate.standardize_date(end, self.timezone)
        )

    def managed_allocations(self) -> Query[Allocation]:
        """ The allocations managed by this scheduler / resource. """
        query = self.session.query(Allocation)
        query = query.filter(Allocation.mirror_of == self.resource)

        return query

    def managed_reserved_slots(self) -> Query[ReservedSlot]:
        """ The reserved_slots managed by this scheduler / resource. """
        uuids = self.managed_allocations().with_entities(Allocation.resource)

        query = self.session.query(ReservedSlot)
        query = query.filter(ReservedSlot.resource.in_(uuids))

        return query

    def managed_reservations(self) -> Query[Reservation]:
        """ The reservations managed by this scheduler / resource. """
        query = self.session.query(Reservation)
        query = query.filter(Reservation.resource == self.resource)

        return query

    def extinguish_managed_records(self) -> None:
        """ WARNING:
        Completely removes any trace of the records managed by this scheduler.
        That means all reservations, reserved slots and allocations!

        """
        self.managed_reservations().delete('fetch')
        self.managed_reserved_slots().delete('fetch')
        self.managed_allocations().delete('fetch')

    def allocation_by_id(self, id: int) -> Allocation:
        query = self.managed_allocations()
        query = query.filter(Allocation.mirror_of == self.resource)
        query = query.filter(Allocation.id == id)
        return query.one()

    def allocations_by_ids(
        self,
        ids: Collection[int]
    ) -> Query[Allocation]:
        query = self.managed_allocations()
        query = query.filter(Allocation.id.in_(ids))
        query = query.order_by(Allocation._start)
        return query

    def allocations_by_group(
        self,
        group: UUID,
        masters_only: bool = True
    ) -> Query[Allocation]:
        return self.allocations_by_groups([group], masters_only=masters_only)

    def allocations_by_groups(
        self,
        groups: Collection[UUID],
        masters_only: bool = True
    ) -> Query[Allocation]:

        query = self.managed_allocations()
        query = query.filter(Allocation.group.in_(groups))

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

    def allocations_by_reservation(
        self,
        token: UUID,
        id: int | None = None
    ) -> Query[Allocation]:
        """ Returns the allocations for the reservation if it was *approved*,
        pending reservations return nothing. If you need to get the allocation
        a pending reservation might be targeting, use _target_allocations
        in model.reservation.

        """

        # TODO -> this is much too joiny, it was easier when we assumed
        # that there would be one reservation per token, now that there
        # is more than one reservation per token we should denormalize
        # this a little by adding the reservation_id to the reserved slot

        groups = self.managed_reservations()
        groups = groups.with_entities(Reservation.target)
        groups = groups.filter(Reservation.token == token)

        if id is not None:
            groups = groups.filter(Reservation.id == id)

        allocations = self.managed_allocations()
        allocations = allocations.with_entities(Allocation.id)
        allocations = allocations.filter(Allocation.group.in_(groups))

        query = self.managed_allocations()
        query = query.join(ReservedSlot)
        query = query.filter(
            ReservedSlot.reservation_token == token
        )
        query = query.filter(
            ReservedSlot.allocation_id.in_(allocations)
        )
        return query

    def allocations_in_range(
        self,
        start: datetime,
        end: datetime,
        masters_only: bool = True
    ) -> Query[Allocation]:

        start, end = self._prepare_range(start, end)

        query = self.managed_allocations()
        query = self.queries.allocations_in_range(query, start, end)

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

    def allocation_by_date(self, start: datetime, end: datetime) -> Allocation:
        query = self.allocations_in_range(start, end)
        return query.one()

    def allocation_dates_by_group(
        self,
        group: UUID
    ) -> list[tuple[datetime, datetime]]:

        query = self.allocations_by_group(group)
        dates_query: Query[tuple[datetime, datetime]] = query.with_entities(
            Allocation._start,
            Allocation._end
        )
        return dates_query.all()

    def allocation_mirrors_by_master(
        self,
        master: Allocation
    ) -> list[Allocation]:
        return [s for s in master.siblings() if not s.is_master]

    def allocation_dates_by_ids(
        self,
        ids: Collection[int],
        start_time: time | None = None,
        end_time: time | None = None
    ) -> Iterator[tuple[datetime, datetime]]:

        for allocation in self.allocations_by_ids(ids).all():

            s = start_time or allocation.display_start().time()
            e = end_time or allocation.display_end().time()

            s_dt, e_dt = allocation.limit_timespan(s, e)

            yield s_dt, e_dt - timedelta(microseconds=1)

    def manual_approval_required(self, ids: Collection[int]) -> bool:
        """ Returns True if any of the allocations require manual approval. """
        query = self.allocations_by_ids(ids)
        query = query.filter(Allocation.approve_manually == True)

        return self.session.query(query.exists()).scalar()  # type: ignore[no-any-return]

    def allocate(
        self,
        dates: _dtrange | Iterable[_dtrange],
        partly_available: bool = False,
        raster: Raster = rasterizer.MIN_RASTER,
        whole_day: bool = False,
        quota: int | None = None,
        quota_limit: int = 0,
        grouped: bool = False,
        data: Any | None = None,
        approve_manually: bool = False,
        skip_overlapping: bool = False,
    ) -> list[Allocation]:
        """ Allocates a spot in the sedate.

        An allocation defines a timerange which can be reserved. No
        reservations can exist outside of existing allocations. In fact any
        reserved slot will link to an allocation.

        :dates:
            The datetimes to allocate. This can be a tuple with start datetime
            and an end datetime object, or a list of tuples with start and end
            datetime objects.

            If the datetime objects are timezone naive they are assumed to be
            of the same timezone as the scheduler itself.

        :partly_available:
            If an allocation is partly available, parts of its daterange may be
            reserved. So if the allocation lats from 01:00 to 03:00, a
            reservation may be made from 01:00 to 02:00.

            if partly_available if False, it may only be reserved as a whole
            (so from 01:00 to 03:00 in the aforementioned example).

            If partly_available is True, a raster may be specified. See
            ``raster``.

        :raster:
            If an allocation is partly available a raster defines the
            granularity with which a reservation can be made.

            For example: a raster of 15min will ensure that reservations are at
            least 15 minutes long and start either at :00, :15, :30 or :45).

            By default, we use a raster of 5, which means that reservations
            may not be shorter than 5 minutes and will snap to 00:05, 00:10,
            00:15 and so on.

            For performance reasons it is not possible to create reservations
            shorter than 5 minutes. If you need that, this library is not for
            you.

        :whole_day:
            If true, the hours/minutes of the given dates are ignored and they
            are made to span a whole day (relative to the scheduler's
            timezone).

        :quota:
            The number of times this allocation may be 'over-reserved'. Say you
            have a concert and you are selling 20 tickets. The concert is on
            saturday night, so there's only one start and end date. But there
            are 20 reservations/tickets that can be made on that allocation.

            By default, an allocation has a quota of one and may therefore
            only be reserved once.

        :quota_limit:
            The number of times a reservation may 'over-reserve' this
            allocation. If you are selling tickets for a concert and set the
            quota_limit to 2, then you are saying that each customer may only
            acquire 2 tickets at once.

            If the quota_limit is 0, there is no limit, which is the default.

        :grouped:
            Creates a grouped allocation. A grouped allocation is an allocation
            spanning multiple date-ranges that may only be reserved as a whole.

            An example for this is a college class which is scheduled to be
            given every tuesday afternoon. A student may either reserve a
            spot for the class as a whole (including all tuesday afternoons),
            or not at all.

            If the allocation has only one start and one end date, the grouped
            parameter has no effect.

            If allocate is called with multiple dates, without grouping, then
            every created allocation is completely independent.

            By default, allocations are not grouped.

        :data:
            A dictionary of your own chosing that will be attached to the
            allocation. Use this for your own data. Note that the dictionary
            needs to be json serializable.

            For more information see :ref:`custom-json`.

        :approve_manually:
            If true, reservations must be approved before they generate
            reserved slots. This allows for a kind fo waitinglist/queue
            that forms around an allocation, giving an admin the possiblity
            to pick the reservations he or she approves of.

            If false, reservations trigger a reserved slots immediatly, which
            results in a first-come-first-serve kind of thing.

            Manual approval is a bit of an anachronism in Libres which **might
            be removed in the future**. We strongly encourage you to not
            use this feature and to just keep the default (which is False).

        :skip_overlapping:
            If true, dates which overlap existing allocations are skipped
            instead of causing an exception.

            Only works if not grouped.

        """
        dates = self._prepare_dates(dates)

        group = new_uuid()
        quota = quota or 1

        # This is mostly for historic reasons - it's unclear if the current
        # code could really handle it..
        if partly_available and grouped:
            raise errors.InvalidAllocationError

        # Groups are all or nothing affairs
        if skip_overlapping and grouped:
            raise errors.InvalidAllocationError

        # the whole day option results in the dates being aligned to
        # the beginning of the day / end of it -> not timezone aware!
        if whole_day:
            for ix, (start, end) in enumerate(dates):
                dates[ix] = sedate.align_range_to_day(
                    start, end, self.timezone
                )

        # Ensure that the list of dates contains no overlaps inside
        rasterized_dates = [
            rasterizer.rasterize_span(s, e, raster) for s, e in dates
        ]

        # We can early out here, since this will create no allocations
        # that way we also don't have to worry about calling min/max
        # with an empty iterable
        if not rasterized_dates:
            return []

        for start, end in rasterized_dates:
            if sedate.count_overlaps(rasterized_dates, start, end) > 1:
                raise errors.InvalidAllocationError
            if end < start:
                raise errors.InvalidAllocationError

        # Make sure that this span does not overlap another master
        skipped = set()

        # Find existing overlapping (master) allocations
        query = self.managed_allocations()
        query = self.queries.overlapping_allocations(query, rasterized_dates)
        query = query.filter(Allocation.resource == self.resource)
        for existing in query:
            # we are doing a bit of redundant work here, since the
            # query doesn't tell us which range(s) the existing
            # allocation overlaps with
            for start, end in rasterized_dates:
                if not sedate.overlaps(
                    start, end,
                    existing.start, existing.end
                ):
                    continue

                if not skip_overlapping:
                    raise errors.OverlappingAllocationError(
                        start, end, existing)
                else:
                    skipped.add((start, end))

        # Write the master allocations
        allocations = []
        for start, end in dates:

            if rasterizer.rasterize_span(start, end, raster) in skipped:
                continue

            allocation = self.allocation_cls()
            allocation.raster = raster
            allocation.start = start
            allocation.end = end
            allocation.timezone = self.timezone
            allocation.resource = self.resource
            allocation.mirror_of = self.resource
            allocation.quota = quota
            allocation.quota_limit = quota_limit
            allocation.partly_available = partly_available
            allocation.approve_manually = approve_manually
            allocation.data = data

            if grouped:
                allocation.group = group
            else:
                allocation.group = new_uuid()

            allocations.append(allocation)

        self.session.add_all(allocations)
        self.session.flush()

        events.on_allocations_added(self.context, allocations)

        return allocations

    def change_quota(self, master: Allocation, new_quota: int) -> None:
        """ Changes the quota of a master allocation.

        Fails if the quota is already exhausted.

        When the quota is decreased a reorganization of the mirrors is
        triggered. Reorganizing means eliminating gaps in the chain of mirrors
        that emerge when reservations are removed:

        Initial State:
        1   (master)    Free
        2   (mirror)    Free
        3   (mirror)    Free

        Reservations are made:
        1   (master)    Reserved
        2   (mirror)    Reserved
        3   (mirror)    Reserved

        A reservation is deleted:
        1   (master)    Reserved
        2   (mirror)    Free     <-- !!
        3   (mirror)    Reserved

        Reorganization is performed:
        1   (master)    Reserved
        2   (mirror)    Reserved <-- !!
        3   (mirror)    Free     <-- !!

        The quota is decreased:
        1   (master)    Reserved
        2   (mirror)    Reserved

        In other words, the reserved allocations are moved to the beginning,
        the free allocations moved at the end. This is done to ensure that
        the sequence of generated uuids for the mirrors always represent all
        possible keys.

        Without the reorganization we would see the following after
        decreasing the quota:

        The quota is decreased:
        1   (master)    Reserved
        3   (mirror)    Reserved

        This would make it impossible to calculate the mirror keys. Instead the
        existing keys would have to queried from the database.

        """

        assert new_quota > 0, 'Quota must be greater than 0'

        if new_quota == master.quota:
            return

        if new_quota > master.quota:
            master.quota = new_quota
            return

        # Make sure that the quota can be decreased
        mirrors = self.allocation_mirrors_by_master(master)
        allocations = [master, *mirrors]

        free_allocations = [a for a in allocations if a.is_available()]

        required = master.quota - new_quota
        if len(free_allocations) < required:
            # FIXME: This seems like a strange error to emit here
            raise errors.AffectedReservationError(None)

        # get a map pointing from the existing uuid to the newly assigned uuid
        reordered = self.reordered_keylist(allocations, new_quota)

        # unused keys are the ones not present in the newly assignd uuid list
        unused = set(reordered.keys()) - set(reordered.values()) - {None}

        # get a map for resource_uuid -> allocation.id
        ids = {a.resource: a.id for a in allocations}

        for allocation in allocations:

            # change the quota for all allocations
            allocation.quota = new_quota

            # the value is None if the allocation is not mapped to a new uuid
            new_resource = reordered[allocation.resource]
            if not new_resource:
                continue

            # move all slots to the mapped allocation id
            new_id = ids[new_resource]

            for slot in allocation.reserved_slots:
                # build a query here as the manipulation of mapped objects in
                # combination with the delete query below seems a bit
                # unpredictable given the cascading of changes

                query = self.session.query(ReservedSlot)
                query = query.filter(and_(
                    ReservedSlot.resource == slot.resource,
                    ReservedSlot.allocation_id == slot.allocation_id,
                    ReservedSlot.start == slot.start
                ))
                query.update(
                    {
                        ReservedSlot.resource: new_resource,
                        ReservedSlot.allocation_id: new_id
                    }
                )

        # get rid of the unused allocations (always preserving the master)
        if unused:
            query = self.session.query(Allocation)
            query = query.filter(Allocation.resource.in_(unused))
            query = query.filter(Allocation.id != master.id)
            query = query.filter(Allocation._start == master._start)
            query.delete('fetch')

    def reordered_keylist(
        self,
        allocations: Collection[Allocation],
        new_quota: int
    ) -> dict[UUID, UUID | None]:
        """ Creates the map for the keylist reorganzation.

        Each key of the returned dictionary is a resource uuid pointing to the
        resource uuid it should be moved to. If the allocation should not be
        moved then key-value is None.

        """
        masters = [a for a in allocations if a.is_master]
        assert len(masters) == 1

        master = masters[0]
        allocation_from_key = {a.resource: a for a in allocations}

        # generate the keylist (the allocation resources may be unordered)
        keylist = [master.resource]
        keylist.extend(utils.generate_uuids(master.resource, master.quota))

        # prefill the map
        reordered: dict[UUID, UUID | None] = {
            k: None
            for k in keylist
        }

        # each free allocation increases the offset by which the next key
        # for a non-free allocation is acquired
        offset = 0
        for ix, key in enumerate(keylist):
            if allocation_from_key[key].is_available():
                offset += 1
            else:
                reordered[key] = keylist[ix - offset]

        return reordered

    def availability(
        self,
        start: datetime | None = None,
        end: datetime | None = None
    ) -> float:
        """Goes through all allocations and sums up the availability."""

        start = start if start else sedate.mindatetime
        end = end if end else sedate.maxdatetime

        start, end = self._prepare_range(start, end)

        return self.queries.availability_by_range(start, end, [self.resource])

    def move_allocation(
        self,
        master_id: int,
        new_start: datetime | None = None,
        new_end: datetime | None = None,
        group: UUID | None = None,
        new_quota: int | None = None,
        approve_manually: bool | None = None,
        quota_limit: int = 0,
        whole_day: bool | None = None,
        data: Any | None = missing
    ) -> None:

        assert master_id
        assert any([new_start and new_end, group, new_quota])

        if new_start is not None and new_end is not None:
            new_start, new_end = self._prepare_range(new_start, new_end)

        # Find allocation
        master = self.allocation_by_id(master_id)
        mirrors = self.allocation_mirrors_by_master(master)

        changing = [master, *mirrors]
        ids = [c.id for c in changing]

        assert master.timezone == self.timezone, """
            You are trying to move an allocation that was created with a
            different timezone. This is currently unsupported. See
            Scheduler.__init__ -> timezone
        """

        assert group or master.group

        # Simulate the new allocation
        new_start = new_start or master.start
        new_end = new_end or master.end

        if whole_day:
            new_start, new_end = sedate.align_range_to_day(
                new_start, new_end, self.timezone
            )

        if new_end < new_start:
            raise errors.InvalidAllocationError

        new = self.allocation_cls(  # type:ignore[misc]
            start=new_start,
            end=new_end,
            raster=master.raster,
            timezone=self.timezone
        )

        # Ensure that the new span does not overlap an existing one
        existing_allocations = self.allocations_in_range(new.start, new.end)

        for existing in existing_allocations:
            if existing.id not in ids:
                raise errors.OverlappingAllocationError(
                    new.start, new.end, existing
                )

        for change in changing:

            if change.partly_available:
                # confirmed reservations
                for reservation in change.reserved_slots:
                    if not new.contains(reservation.start, reservation.end):
                        raise errors.AffectedReservationError(reservation)

                # pending reservations
                if change.is_master:  # (mirrors return the same values)
                    for pending in change.pending_reservations.with_entities(
                            Reservation.start, Reservation.end):
                        if not new.contains(*pending):
                            raise errors.AffectedPendingReservationError(
                                pending
                            )

            else:
                # confirmed reservations
                if change.start != new.start or change.end != new.end:
                    if len(change.reserved_slots):
                        raise errors.AffectedReservationError(
                            change.reserved_slots[0]
                        )

                    if (
                        change.is_master and
                        change.pending_reservations.count()
                    ):
                        raise errors.AffectedPendingReservationError(
                            change.pending_reservations[0]
                        )

        # the following attributes must be equal over all group members
        # (this still allows to use move_allocation to remove an allocation
        #  from an existing group by specifiying the new group)
        for allocation in self.allocations_by_group(group or master.group):

            if approve_manually is not None:
                allocation.approve_manually = approve_manually

            if quota_limit is not None:
                allocation.quota_limit = quota_limit

            if new_quota is not None and allocation.is_master:
                self.change_quota(allocation, new_quota)

        for change in changing:
            change.start = new.start
            change.end = new.end
            change.group = group or master.group

            if data is not missing:
                change.data = data

    @overload
    def remove_allocation(self, id: int) -> None: ...

    @overload
    def remove_allocation(
        self,
        id: None = ...,
        *,
        groups: Collection[UUID]
    ) -> None: ...

    def remove_allocation(
        self,
        id: int | None = None,
        groups: Collection[UUID] | None = None
    ) -> None:

        allocations: Iterable[Allocation]
        if id:
            # FIXME: We probably should `assert groups is None`
            #        since the parameter does nothing if `id` is
            #        given. But we might break some existing code
            #        which has been using this incorrectly...
            master = self.allocation_by_id(id)
            allocations = [master]
            allocations.extend(self.allocation_mirrors_by_master(master))
        elif groups:
            allocations = self.allocations_by_groups(
                groups, masters_only=False
            )
        else:
            raise NotImplementedError

        for allocation in allocations:
            assert allocation.mirror_of == self.resource, """
                Trying to delete an allocation from a different resource than
                the scheduler and context. This is a serious error or
                someone trying to something funny with the POST parameters.
            """

            if allocation.is_transient:
                # the allocation doesn't exist yet, so we can't delete it
                continue

            if len(allocation.reserved_slots) > 0:
                raise errors.AffectedReservationError(
                    allocation.reserved_slots[0]
                )

            if allocation.pending_reservations.count():
                raise errors.AffectedPendingReservationError(
                    allocation.pending_reservations[0]
                )

        for allocation in allocations:
            if not allocation.is_transient:
                self.session.delete(allocation)

    def remove_unused_allocations(
        self,
        start: DateLike,
        end: DateLike,
        days: Iterable[Day | DayNumber] | None = None,
        exclude_groups: bool = False
    ) -> int:
        """ Removes all allocations without reservations between start and
        end and returns the number of allocations that were deleted.

        Groups which are partially inside the daterange are not included.

        :days:
            List of days which should be considered, a subset of:
            (['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su'])

            If left out or empty, all days are included.

        :exclude_groups:
            Whether or not grouped allocations should ever be removed

            If days is set to a subset of a full week, groups will always
            be excluded, regardless of what this parameter is set to.
        """

        start_dt, end_dt = self._prepare_range(
            sedate.as_datetime(start),
            sedate.as_datetime(end)
        )

        day_numbers: set[DayNumber] | None = None
        if days:
            # get the day from the map - if impossible take the verbatim value
            # this allows for using strings or integers
            day_numbers = {
                DAYS_MAP.get(day, day)  # type:ignore[arg-type]
                for day in days
            }
            if day_numbers.issuperset(DAYS_MAP.values()):
                # if all days are allowed we just unset the filter
                day_numbers = None

            exclude_groups = True
        else:
            day_numbers = None

        # all the slots
        slots = self.managed_reserved_slots()
        slots = slots.with_entities(ReservedSlot.allocation_id)

        # all the reservations
        reservations = self.managed_reservations()
        reservations = reservations.with_entities(Reservation.target)

        # all the groups which are fully inside the required scope
        groups = self.managed_allocations().with_entities(Allocation.group)
        groups = groups.group_by(Allocation.group)
        if exclude_groups:
            # FIXME: For now we only allow ungrouped allocations
            #        if a days filter is set, othewise we would
            #        need to make this function far more complicated
            #        or reuse the search function and make this
            #        function generally a lot slower
            groups = groups.having(
                and_(
                    func.count(Allocation.id) == 1,
                    start_dt <= func.min(Allocation._start),
                    func.max(Allocation._end) <= end_dt
                )
            )
        else:
            groups = groups.having(
                and_(
                    start_dt <= func.min(Allocation._start),
                    func.max(Allocation._end) <= end_dt
                )
            )

        # all allocations
        candidates = self.managed_allocations()
        candidates = candidates.filter(start_dt <= Allocation._start)
        candidates = candidates.filter(Allocation._end <= end_dt)

        # .. without the ones with slots
        candidates = candidates.filter(not_(Allocation.id.in_(slots)))

        # .. without the ones with reservations
        candidates = candidates.filter(
            not_(Allocation.group.in_(reservations))
        )

        # .. including only the groups fully inside the required scope
        allocations = candidates.filter(Allocation.group.in_(groups))

        if not day_numbers:
            # we can just emit a simple DELETE query
            return allocations.delete('fetch')

        # we need to filter by weekday which we cannot easily do in SQL
        # so we fetch first and delete the allocations that match
        deleted = 0
        for allocation in allocations:
            if allocation.display_start().weekday() not in day_numbers:
                continue

            self.session.delete(allocation)
            deleted += 1
        return deleted

    @overload
    def reserve(
        self,
        email: str,
        dates: _dtrange | Collection[_dtrange],
        group: None = ...,
        data: Any | None = ...,
        session_id: UUID | None = ...,
        quota: int = ...,
        single_token_per_session: bool = ...
    ) -> UUID: ...

    @overload
    def reserve(
        self,
        email: str,
        dates: None,
        group: UUID,
        data: Any | None = ...,
        session_id: UUID | None = ...,
        quota: int = ...,
        single_token_per_session: bool = ...
    ) -> UUID: ...

    @overload
    def reserve(
        self,
        email: str,
        dates: None = ...,
        *,
        group: UUID,
        data: Any | None = ...,
        session_id: UUID | None = ...,
        quota: int = ...,
        single_token_per_session: bool = ...
    ) -> UUID: ...

    def reserve(
        self,
        email: str,
        dates: _dtrange | Collection[_dtrange] | None = None,
        group: UUID | None = None,
        data: Any | None = None,
        session_id: UUID | None = None,
        quota: int = 1,
        single_token_per_session: bool = False
    ) -> UUID:
        """ Reserves one or many allocations. Returns a token that needs
        to be passed to :meth:`approve_reservations` to complete the
        reservation.

        That is to say, Libres uses a two-step reservation process. The first
        step is reserving what is either an open spot or a place on the
        waiting list (see ``approve_manually`` of
        :meth:`~libres.db.scheduler.Scheduler.allocate`).

        The second step is to actually write out the reserved slots, which
        is done by approving an existing reservation.

        Most checks are done in the reserve functions. The approval step
        only fails if there's no open spot.

        This function returns a reservation token which can be used to
        approve the reservation in approve_reservation.

        Usually you want to just short-circuit those two steps::

            scheduler.approve_reservations(
                scheduler.reserve(dates)
            )

        :email:
            Each reservation *must* be associated with an email. That is, a
            user.

        :dates:
            The dates to reserve. May either be a tuple of start/end datetimes
            or a list of such tuples.

        :group:
            The allocation group to reserve. ``dates``and ``group`` are
            mutually exclusive.

        :data:
            A dictionary of your own chosing that will be attached to the
            reservation. Use this for your own data. Note that the dictionary
            needs to be json serializable.

            For more information see :ref:`custom-json`.

        :session_id:
            An uuid that connects the reservation to a browser session.

            Together with
            :meth:`libres.db.queries.Queries.confirm_reservations_for_session`
            this can be used to create a reservation shopping card.

            By default the session_id is None, meaning that no browser session
            is associated with the reservation.

        :quota:
            The number of allocations that should be reserved at once. See
            ``quota`` in :meth:`~libres.db.scheduler.Scheduler.allocate`.

        :single_token_per_session:
            If True, all reservations of the same session shared the same
            token, though that token will differ from the session id itself.

            This only applies if the reserve function is called multiple times
            with the same session id. In this case, subsequent reserve calls
            will re-use whatever token they can find in the table.

            If there's no existing reservations, a new token will be created.
            That also applies if a reservation is created, deleted and then
            another is created. Because the last reserve call won't find any
            reservations it will create a new token.

            So the shared token is always the last token returned by the
            reserve function.

            Note that this only works reliably if you set this parameter to
            true for *all* your reserve calls that use a session.

        """

        assert (dates or group) and not (dates and group)

        email = email.strip()

        if not self.validate_email(email):
            raise errors.InvalidEmailAddress

        if group:
            dates = self.allocation_dates_by_group(group)

        assert dates is not None
        dates = self._prepare_dates(dates)
        timezone = self.timezone

        # First, the request is checked for saneness. If any requested
        # date cannot be reserved the request as a whole fails.
        for start, end in dates:

            # are the parameters valid?
            if not utils.is_valid_reservation_length(start, end, timezone):
                raise errors.ReservationTooLong

            if start > end or (end - start).seconds < 5 * 60:
                raise errors.ReservationTooShort

            # can all allocations be reserved?
            for allocation in self.allocations_in_range(start, end):

                # start and end are not rasterized, so we need this check
                if not allocation.overlaps(start, end):
                    continue

                assert allocation.is_master

                # with manual approval the reservation ends up on the
                # waitinglist and does not yet need a spot
                if not allocation.approve_manually:
                    if not allocation.find_spot(start, end):
                        raise errors.AlreadyReservedError

                    free = self.free_allocations_count(allocation, start, end)
                    if free < quota:
                        raise errors.AlreadyReservedError

                if not allocation.contains(start, end):
                    raise errors.TimerangeTooLong()

                if 0 < allocation.quota_limit < quota:
                    raise errors.QuotaOverLimit

                if allocation.quota < quota:
                    raise errors.QuotaImpossible

                if quota < 1:
                    raise errors.InvalidQuota

        # ok, we're good to go
        if single_token_per_session and session_id:
            existing = self.queries.reservations_by_session(session_id).first()
            token = existing and existing.token or new_uuid()
        else:
            token = new_uuid()

        # groups are reserved by group-identifier - so all members of a group
        # or none of them. As such there's no start / end date which is defined
        # implicitly by the allocation
        def new_reservations_by_group(
            group: UUID | None
        ) -> Iterator[Reservation]:

            if group:
                reservation = self.reservation_cls()
                reservation.token = token
                reservation.target = group
                reservation.status = 'pending'
                reservation.target_type = 'group'
                reservation.resource = self.resource
                reservation.data = data
                reservation.session_id = session_id
                reservation.email = email.strip()
                reservation.quota = quota

                yield reservation

        # all other reservations are reserved by start/end date
        def new_reservations_by_dates(
            dates: list[tuple[datetime, datetime]]
        ) -> Iterator[Reservation]:

            already_reserved_groups = set()

            for start, end in dates:
                for allocation in self.allocations_in_range(start, end):
                    if allocation.group in already_reserved_groups:
                        continue

                    if not allocation.overlaps(start, end):
                        continue

                    # automatically reserve the whole group if the allocation
                    # is part of a group
                    if allocation.in_group:
                        already_reserved_groups.add(allocation.group)

                        yield from new_reservations_by_group(allocation.group)
                    else:
                        reservation = self.reservation_cls()
                        reservation.token = token
                        reservation.start, reservation.end\
                            = rasterizer.rasterize_span(
                                start, end, allocation.raster
                            )
                        reservation.timezone = allocation.timezone
                        reservation.target = allocation.group
                        reservation.status = 'pending'
                        reservation.target_type = 'allocation'
                        reservation.resource = self.resource
                        reservation.data = data
                        reservation.session_id = session_id
                        reservation.email = email.strip()
                        reservation.quota = quota

                        yield reservation

        # create the reservations
        if group:
            reservations = tuple(new_reservations_by_group(group))
        else:
            reservations = tuple(new_reservations_by_dates(dates))

        if not reservations:
            raise errors.InvalidReservationError

        # have a very simple overlap check for reservations, it's not important
        # that this catches *all* possible problems - that's being handled
        # by the reservation slots - but it should stop us from adding the same
        # reservation twice on a single session
        if session_id:
            found = self.queries.reservations_by_session(session_id)
            found_set: set[tuple[UUID, datetime | None]] = set(
                found.with_entities(Reservation.target, Reservation.start)
            )

            for reservation in reservations:
                if (reservation.target, reservation.start) in found_set:
                    raise errors.OverlappingReservationError

        for reservation in reservations:
            self.session.add(reservation)

        events.on_reservations_made(self.context, reservations)

        return token

    def _approve_reservation_record(
        self,
        reservation: Reservation
    ) -> list[ReservedSlot]:

        # write out the slots
        slots_to_reserve = []

        dates: tuple[_dtrange, ...] | list[_dtrange]
        if reservation.target_type == 'group':
            dates = self.allocation_dates_by_group(reservation.target)
        else:
            assert reservation.start is not None
            assert reservation.end is not None
            dates = ((reservation.start, reservation.end),)

        # the reservation quota is simply implemented by multiplying the
        # dates which are approved

        dates = dates * reservation.quota

        for start, end in dates:

            for allocation in self.reservation_targets(start, end):

                allocation_slots = allocation.all_slots(start, end)

                for slot_start, slot_end in allocation_slots:
                    slot = ReservedSlot()
                    slot.start = slot_start
                    slot.end = slot_end
                    slot.resource = allocation.resource
                    slot.reservation_token = reservation.token

                    # the slots are written with the allocation
                    allocation.reserved_slots.append(slot)
                    slots_to_reserve.append(slot)

                # the allocation may be a fake one, in which case we
                # must make it realz yo
                if allocation.is_transient:
                    self.session.add(allocation)

        reservation.status = 'approved'

        if not slots_to_reserve:
            raise errors.NotReservableError

        return slots_to_reserve

    def approve_reservations(self, token: UUID) -> list[ReservedSlot]:
        """ This function approves an existing reservation and writes the
        reserved slots accordingly.

        Returns a list with the reserved slots.

        """

        slots_to_reserve = []

        reservations = self.reservations_by_token(token).all()

        try:
            for reservation in reservations:
                slots_to_reserve.extend(
                    self._approve_reservation_record(reservation)
                )
        except errors.LibresError as e:
            e.reservation = reservation
            raise e

        events.on_reservations_approved(self.context, reservations)

        return slots_to_reserve

    def deny_reservation(self, token: UUID) -> None:
        """ Denies a pending reservation, removing it from the records and
        sending an email to the reservee.

        """

        query = self.reservations_by_token(token)
        query = query.filter(Reservation.status == 'pending')

        reservations = query.all()

        query.delete()

        events.on_reservations_denied(self.context, reservations)

    def remove_reservation(
        self,
        token: UUID,
        id: int | None = None
    ) -> None:
        """ Removes all reserved slots of the given reservation token.

        Note that removing a reservation does not let the reservee know that
        his reservation has been removed.

        If you want to let the reservee know what happened,
        use revoke_reservation.

        The id is optional. If given, only the reservation with the given
        token AND id is removed.

        """

        slots = self.reserved_slots_by_reservation(token, id).all()

        for slot in slots:
            self.session.delete(slot)

        reservations = self.reservations_by_token(token, id).all()

        for reservation in reservations:
            self.session.delete(reservation)

        # some allocations still reference reserved_slots if not for this
        self.session.expire_all()

        events.on_reservations_removed(self.context, reservations)

    def change_email(self, token: UUID, new_email: str) -> None:

        for reservation in self.reservations_by_token(token).all():
            reservation.email = new_email

    def change_reservation_data(
        self,
        token: UUID,
        data: Any | None
    ) -> None:

        for reservation in self.reservations_by_token(token).all():
            reservation.data = data

    def change_reservation_time_candidates(
        self,
        tokens: Collection[UUID] | None = None
    ) -> Query[Reservation]:
        """ Returns the reservations that fullfill the restrictions
        imposed by change_reservation_time.

        Pass a list of reservation tokens to further limit the results.

        """

        query = self.managed_reservations()
        query = query.filter(Reservation.status == 'approved')
        query = query.filter(Reservation.target_type == 'allocation')

        groups = self.managed_allocations().with_entities(Allocation.group)
        groups = groups.filter(Allocation.partly_available == True)

        query = query.filter(Reservation.target.in_(groups))

        if tokens:
            query = query.filter(Reservation.token.in_(tokens))

        return query

    def change_reservation_time(
        self,
        token: UUID,
        id: int,
        new_start: datetime,
        new_end: datetime
    ) -> Reservation | None:
        """ Kept for backwards compatibility, use :meth:`change_reservation`
        instead.

        """
        import warnings
        warnings.warn(
            'change_reservation_time is deprecated and will be removed '
            'in a future version, please use change_reservation instead.',
            DeprecationWarning,
            stacklevel=2
        )
        return self.change_reservation(token, id, new_start, new_end)

    def change_reservation(
        self,
        token: UUID,
        id: int,
        new_start: datetime,
        new_end: datetime,
        quota: int | None = None
    ) -> Reservation | None:
        """ Allows to change the timespan of a reservation under certain
        conditions:

        - The new timespan must be reservable inside the existing allocation.
          (So you cannot use this method to reserve another allocation)
        - The referenced allocation must not be in a group.

        Returns the new reservation if a change was made and None instead.

        Just like revoke_reservation, this function raises an event which
        includes a send_email flag and a reason which may be used to inform
        the user of the changes to his reservation.

        """

        # check for the reservation first as the allocation won't exist
        # if the reservation has not been approved yet
        assert new_start and new_end

        new_start, new_end = self._prepare_range(new_start, new_end)
        existing_reservation = self.reservations_by_token(token, id).one()

        # if there's nothing to change, do not change
        if quota is None or existing_reservation.quota == quota:  # noqa: SIM102
            if existing_reservation.start == new_start:
                ends = (new_end, new_end - timedelta(microseconds=1))

                if existing_reservation.end in ends:
                    return None

        # will return raise a MultipleResultsFound exception if this is a group
        if existing_reservation.status == 'approved':
            allocation = self.allocations_by_reservation(token, id).one()
        else:
            _allocation = existing_reservation._target_allocations().first()
            assert _allocation is not None
            allocation = _allocation

        if not allocation.contains(new_start, new_end):
            raise errors.TimerangeTooLong()

        reservation_arguments: _ReserveArgs = {
            'email': existing_reservation.email,
            'dates': (new_start, new_end),
            'data': existing_reservation.data,
            'quota': quota or existing_reservation.quota
        }

        old_start = existing_reservation.display_start()
        old_end = existing_reservation.display_end()

        with self.begin_nested():
            self.remove_reservation(token, id)

            new_token = self.reserve(**reservation_arguments)
            new_reservation = self.reservations_by_token(new_token).one()
            new_reservation.id = id
            new_reservation.token = token
            new_reservation.session_id = existing_reservation.session_id

            if existing_reservation.status == 'approved':
                self._approve_reservation_record(new_reservation)

            events.on_reservation_time_changed(
                self.context,
                new_reservation,
                old_time=(old_start, old_end),
                new_time=(
                    new_reservation.display_start(),
                    new_reservation.display_end()
                ),
            )

        return new_reservation

    def search_allocations(
        self,
        start: datetime,
        end: datetime,
        days: Collection[Day | DayNumber] | None = None,
        minspots: int = 0,
        available_only: bool = False,
        whole_day: Literal['any', 'yes', 'no'] = 'any',
        groups: Literal['any', 'yes', 'no'] = 'any',
        strict: bool = False
    ) -> list[Allocation]:
        """ Search allocations using a number of options. The date is split
        into date/time. All allocations between start and end date within
        the given time (on each day) are included.

        For example, start=01.01.2012 12:00 end=31.01.2012 14:00 will include
        all allocations in January 2012 which OVERLAP the given times. So an
        allocation starting at 11:00 and ending at 12:00 will be included!

        WARNING allocations not matching the start/end date may be included
        if they belong to a group from which a member *is* included!

        If that behavior is not wanted set 'strict' to True
        or set 'include_groups' to 'no' (though you won't get any groups then).

        Allocations which are included in this way will return True in the
        following expression:

        getattr(allocation, 'is_extra_result', False)

        :start:
            Include allocations starting on or after this date.

        :end:
            Include allocations ending on or before this date.

        :days:
            List of days which should be considered, a subset of:
            (['mo', 'tu', 'we', 'th', 'fr', 'sa', 'su'])

            If left out, all days are included.

        :minspots:
            Minimum number of spots reservable.

        :available_only:
            If True, unavailable allocations are left out
            (0% availability). Default is False.

        :whole_day:
            May have one of the following values: 'yes', 'no', 'any'

            If yes, only whole_day allocations are returned.
            If no, whole_day allocations are filtered out.
            If any (default), all allocations are included.

            Any is the same as leaving the option out.

        :groups:
            'any' if all allocations should be included.
            'yes' if only group-allocations should be included.
            'no' if no group-allocations should be included.

            See allocation.in_group to see what constitutes a group

        :strict:
            Set to True if you don't want groups included as a whole if a
            groupmember is found. See comment above.
        """

        assert start
        assert end

        start, end = self._prepare_range(start, end)

        assert whole_day in ('yes', 'no', 'any')
        assert groups in ('yes', 'no', 'any')

        day_numbers: set[DayNumber] | None
        if days:
            # get the day from the map - if impossible take the verbatim value
            # this allows for using strings or integers
            day_numbers = {
                DAYS_MAP.get(day, day)  # type:ignore[arg-type]
                for day in days
            }
        else:
            day_numbers = None

        query = self.allocations_in_range(start, end)
        query = query.order_by(Allocation._start)

        allocations = []

        known_groups = set()
        known_ids = set()

        for allocation in query.all():

            if not self.is_allocation_exposed(allocation):
                continue

            s = datetime.combine(allocation.start.date(), start.time())
            e = datetime.combine(allocation.end.date(), end.time())

            # the raw dates will be UTC
            s = sedate.replace_timezone(s, 'UTC')
            e = sedate.replace_timezone(e, 'UTC')

            if not allocation.overlaps(s, e):
                continue

            if (
                day_numbers
                and allocation.display_start().weekday() not in day_numbers
            ):
                continue

            if whole_day != 'any':
                if whole_day == 'yes' and not allocation.whole_day:
                    continue
                if whole_day == 'no' and allocation.whole_day:
                    continue

            # minspots means that we don't show allocations which cannot
            # be reserved with the required spots in one reservation
            # so we can disregard all allocations with a lower quota limit.
            #
            # the spots are later checked again for actual availability, but
            # that is a heavier check, so it doesn't belong here.
            if minspots and (0 < allocation.quota_limit < minspots):
                continue

            if available_only and not allocation.find_spot(s, e):
                continue

            if minspots:
                availability = self.availability(
                    allocation.start, allocation.end
                )

                if (minspots / float(allocation.quota) * 100.0) > availability:
                    continue

            # keep track of allocations in groups as those need to be added
            # to the result, even though they don't match the search
            in_group = (
                allocation.group in known_groups or allocation.in_group
            )

            if in_group:
                known_groups.add(allocation.group)
                known_ids.add(allocation.id)

            if groups != 'any':
                if groups == 'yes' and not in_group:
                    continue
                if groups == 'no' and in_group:
                    continue

            allocations.append(allocation)

        if not strict and groups != 'no' and known_ids and known_groups:
            query = self.managed_allocations()
            query = query.filter(not_(Allocation.id.in_(known_ids)))
            query = query.filter(Allocation.group.in_(known_groups))

            for allocation in query.all():
                allocation.is_extra_result = True  # type:ignore[attr-defined]
                allocations.append(allocation)

            allocations.sort(key=attrgetter('_start'))

        return allocations

    def free_allocations_count(
        self,
        master_allocation: Allocation,
        start: datetime,
        end: datetime
    ) -> int:
        """ Returns the number of free allocations between master_allocation
        and it's mirrors.

        """

        free_allocations = 0

        if master_allocation.is_available(start, end):
            free_allocations += 1

        if master_allocation.quota == 1:
            return free_allocations

        for mirror in self.allocation_mirrors_by_master(master_allocation):
            if mirror.is_available(start, end):
                free_allocations += 1

        return free_allocations

    def reservation_targets(
        self,
        start: datetime,
        end: datetime
    ) -> list[Allocation]:
        """ Returns a list of allocations that are free within start and end.
        These allocations may come from the master or any of the mirrors.

        """
        targets = []

        query = self.queries.all_allocations_in_range(start, end)
        query = query.filter(Allocation.resource == self.resource)

        for master_allocation in query:

            if not master_allocation.overlaps(start, end):
                continue  # may happen because start and end are not rasterized

            found = master_allocation.find_spot(start, end)

            if not found:
                raise errors.AlreadyReservedError

            targets.append(found)

        return targets

    def reserved_slots_by_reservation(
        self,
        token: UUID,
        id: int | None = None
    ) -> Query[ReservedSlot]:
        """ Returns all reserved slots of the given reservation.
        The id is optional and may be used only return the slots from a
        specific reservation matching token and id.
        """

        assert token

        query = self.managed_reserved_slots()
        query = query.filter(ReservedSlot.reservation_token == token)

        if id is None:
            return query
        else:
            allocations = self.allocations_by_reservation(token, id)
            ids = allocations.with_entities(Allocation.id)
            return query.filter(ReservedSlot.allocation_id.in_(ids))

    def reservations_by_group(self, group: UUID) -> Query[Reservation]:
        tokens = self.managed_reservations().with_entities(Reservation.token)
        tokens = tokens.filter(Reservation.target == group)

        return self.managed_reservations().filter(
            Reservation.token.in_(tokens)
        )

    def reservations_by_allocation(
        self,
        allocation_id: int
    ) -> Query[Reservation]:

        master = self.allocation_by_id(allocation_id)
        return self.reservations_by_group(master.group)

    def reservations_by_token(
        self,
        token: UUID,
        id: int | None = None
    ) -> Query[Reservation]:

        query = self.managed_reservations()
        query = query.filter(Reservation.token == token)

        if id:
            query = query.filter(Reservation.id == id)

        try:
            query.first()
        except exc.NoResultFound:
            raise errors.InvalidReservationToken from None

        return query
