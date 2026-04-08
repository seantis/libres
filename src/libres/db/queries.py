from __future__ import annotations

import logging
import sedate

from datetime import date, datetime, timedelta
from itertools import groupby
from libres.context.core import ContextServicesMixin
from libres.db.models import Allocation, Reservation, ReservedSlot
from libres.db.models.types import UTCDateTime
from libres.modules import errors, events, rasterizer
from operator import itemgetter
from sqlalchemy import column, func, text, type_coerce
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import and_, or_


from typing import TypeVar
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterable
    from collections.abc import Iterator
    from sqlalchemy.orm import Query
    from uuid import UUID

    from libres.context.core import Context

_T = TypeVar('_T')


log = logging.getLogger('libres')


class Queries(ContextServicesMixin):
    """ Contains helper methods independent of the resource (as owned by
    :class:`.scheduler.Scheduler`)

    Some contained methods require the current context (for the session).
    Some contained methods do not require any context, they are marked
    as staticmethods.

    """

    def __init__(self, context: Context):
        self.context = context

    def all_allocations_in_range(
        self,
        start: datetime,
        end: datetime
    ) -> Query[Allocation]:
        return self.allocations_in_range(
            self.session.query(Allocation), start, end
        )

    @staticmethod
    def allocations_in_range(
        query: Query[_T],
        start: datetime,
        end: datetime
    ) -> Query[_T]:
        """ Takes an allocation query and limits it to the allocations
        overlapping with start and end.

        """
        return query.filter(
            or_(
                and_(
                    Allocation._start <= start,
                    start <= Allocation._end
                ),
                and_(
                    start <= Allocation._start,
                    Allocation._start <= end
                )
            )
        )

    @staticmethod
    def overlapping_allocations(
        query: Query[_T],
        dates: Iterable[tuple[datetime, datetime]]
    ) -> Query[_T]:
        """ Takes an allocation query and limits it to the allocations
        overlapping with any of the passed in datetime ranges

        """
        return query.filter(or_(*(
            or_(
                and_(
                    Allocation._start <= start,
                    start <= Allocation._end
                ),
                and_(
                    start <= Allocation._start,
                    Allocation._start <= end
                )
            )
            for start, end in dates
        )))

    @staticmethod
    def availability_by_allocations(
        allocations: Iterable[Allocation]
    ) -> float:
        """Takes any iterable with alloctions and calculates the availability.
        Counts missing mirrors as 100% free and returns a value between 0-100
        in any case.
        For single allocations check the allocation.availability property.

        """
        total, expected_count, count = 0.0, 0, 0
        for allocation in allocations:
            total += allocation.availability
            count += 1

            # Sum up the expected number of allocations. Missing allocations
            # indicate mirrors that have not yet been physically created.
            if allocation.is_master:
                expected_count += allocation.quota

        if not expected_count:
            return 0

        missing = expected_count - count
        total += missing * 100

        return total / expected_count

    def reserved_slots_by_range(
        self,
        start: datetime,
        end: datetime,
        resource: UUID,
        blocking_resources: Collection[UUID],
    ) -> tuple[dict[datetime, int], set[datetime]]:
        """ Returns two lookups for reserved slots for the given resource
        and the given blocking resources.

        The first lookup is a ``dict`` containing reserved slot start times in
        :attr:`~libres.modules.rasterizer.MIN_RASTER` minute slices and
        the corresponding used up quota. The second is a ``set`` containing
        the same slices but for reservation blockers, which always use up
        all the remaining quota.

        This method can be used when blocking resources are involved, since
        :attr:`~libres.db.models.allocation.Allocation.availability` and
        :meth:`~libres.db.models.allocation.Allocation.availability_partitions`
        only take into account the linked resource.

        """
        start, end = rasterizer.rasterize_span(
            start, end, rasterizer.MIN_RASTER
        )

        slot_series = func.generate_series(
            type_coerce(start, UTCDateTime),
            type_coerce(end, UTCDateTime),
            timedelta(minutes=rasterizer.MIN_RASTER)
        ).table_valued(column('slot', UTCDateTime)).render_derived()
        reserved_slots = self.session.query(
            ReservedSlot.source_type,
            slot_series.c.slot,
            func.count(text('1')).label('quota')
        ).join(
            ReservedSlot,
            and_(
                func.tsrange(
                    ReservedSlot.start,
                    ReservedSlot.end
                ).op('@>')(slot_series.c.slot),
                ReservedSlot.resource.in_({resource, *blocking_resources})
            )
        ).group_by(
            ReservedSlot.source_type,
            slot_series.c.slot
        ).order_by(ReservedSlot.source_type)
        reserved: dict[datetime, int] = {}
        blocked: set[datetime] = set()
        for source_type, slots_group in groupby(
            reserved_slots,
            key=itemgetter(0)
        ):
            if source_type == 'reservation':
                reserved = {
                    slot: quota
                    for _, slot, quota in slots_group
                }
            elif source_type == 'blocker':
                blocked = {slot for _, slot, _ in slots_group}
        return reserved, blocked

    def availability_and_partitions_by_allocations(
        self,
        allocations: Collection[Allocation],
        resource: UUID,
        blocking_resources: Collection[UUID],
        normalize_dst: bool = True,
    ) -> Iterator[tuple[Allocation, float, list[tuple[float, bool]]]]:
        """ Takes any collection of alloctions and for each allocation
        calculates the availability and availability partitions for the
        given resource and the given  blocking resources.

        This method should be used when blocking resources are involved, since
        :attr:`~libres.db.models.allocation.Allocation.availability` and
        :meth:`~libres.db.models.allocation.Allocation.availability_partitions`
        only take into account the linked resource.

        """
        if not allocations:
            return

        reserved, blocked = self.reserved_slots_by_range(
            min(allocation._start for allocation in allocations),
            max(allocation._end for allocation in allocations),
            resource=resource,
            blocking_resources=blocking_resources
        )

        # NOTE: This yields a sequence of partitions with two boolean values
        #       corresponding to whether or not the slot is reserved at all
        #       and whether it is reserved by a blocker
        def iter_partitions(
            slots: Iterable[tuple[datetime, datetime] | tuple[None, None]]
        ) -> Iterator[tuple[bool, bool]]:
            for start, end in slots:
                if start is None:
                    yield True, False
                    continue

                # NOTE: Since the slots on the allocation may be larger
                #       than the minimum raster, we need to rasterize
                #       each slot into subslots, to check if any of
                #       them overlap.
                is_reserved = False
                is_blocked = False
                for slot, _ in rasterizer.iterate_span(
                    start,
                    end,  # type: ignore[arg-type]
                    rasterizer.MIN_RASTER
                ):
                    if slot in blocked:
                        is_reserved = is_blocked = True
                        break

                    if slot in reserved:
                        is_reserved = True
                yield is_reserved, is_blocked

        for allocation in allocations:
            if not allocation.partly_available:
                # NOTE: simple case, just return one partition with the total
                #       availability based on allocation.quota, the maximum
                #       amount of overlaps with any sub-partition accounts
                #       for the total used quota
                quota_used = max(
                    (
                        allocation.quota
                        if slot in blocked
                        else reserved.get(slot, 0)
                        for slot, _ in rasterizer.iterate_span(
                            allocation._start,
                            allocation._end,
                            rasterizer.MIN_RASTER
                        )
                    ),
                    default=0
                )
                quota_left = max(0, allocation.quota - quota_used)
                yield (
                    allocation,
                    100.0 * quota_left / allocation.quota,
                    [(100.0, quota_left == 0)]
                )
                continue

            # TODO: For now we don't support allocations with mirrors that
            #       are partly available. It would be possible to support
            #       by slightly altering the algorithm, but it would be
            #       more expensive, than what we're doing right now. We never
            #       use this specific combination of features in our
            #       applications so it's not worth implementing this branch
            #       yet.
            if allocation.quota > 1:
                raise NotImplementedError

            if normalize_dst:
                slots = tuple(allocation.normalized_slots())
            else:
                slots = tuple(allocation.all_slots())

            step = 100.0 / float(len(slots))
            partitions = []
            total = 0.0
            blocked_num = 0
            reserved_num = 0
            for flag, _group in groupby(
                iter_partitions(slots),
                key=itemgetter(0)
            ):
                group = tuple(_group)
                percentage = len(group) * step
                partitions.append((percentage, flag))
                total += percentage
                if flag:
                    group_blocked_num = sum(1 for item in group if item[1])
                    reserved_num += len(group) - group_blocked_num
                    blocked_num += group_blocked_num

            # Make sure to get rid of floating point rounding errors
            diff = 100.0 - total
            if partitions:
                percentage, flag = partitions[-1]
                partitions[-1] = (percentage - diff, flag)

            # Calculate the availability based on the number of slots
            total_num = len(slots)
            if total_num == blocked_num:
                availability = 0.0
            elif reserved_num == 0:
                availability = 100.0
            else:
                total_num -= blocked_num
                if total_num <= reserved_num:
                    availability = 0.0
                else:
                    availability = 100.0 - 100.0 * (reserved_num / total_num)
            yield allocation, availability, partitions

    def allocations_with_availability_by_range(
        self,
        start: datetime,
        end: datetime,
        resource: UUID,
        blocking_resources: Collection[UUID],
        normalize_dst: bool = True,
    ) -> Iterator[tuple[Allocation, float, list[tuple[float, bool]]]]:
        """ Yields a sequence of all allocations along with their availability
        and availability partitions for the given resource and the given
        blocking resources.

        This method should be used when blocking resources are involved, since
        :attr:`~libres.db.models.allocation.Allocation.availability` and
        :meth:`~libres.db.models.allocation.Allocation.availability_partitions`
        only take into account the linked resource.

        """

        query = self.all_allocations_in_range(start, end)
        query = query.filter(Allocation.mirror_of == resource)
        query = query.filter(Allocation.resource == resource)

        return self.availability_and_partitions_by_allocations(
            tuple(a for a in query if self.is_allocation_exposed(a)),
            resource=resource,
            blocking_resources=blocking_resources,
            normalize_dst=normalize_dst
        )

    def availability_by_range(
        self,
        start: datetime,
        end: datetime,
        resources: Collection[UUID]
    ) -> float:
        """Returns the availability for the given resources in the given range.
        The exposure is used to check if the allocation is visible.

        """

        query = self.all_allocations_in_range(start, end)
        query = query.filter(Allocation.mirror_of.in_(resources))
        query = query.options(joinedload(Allocation.reserved_slots))

        allocations = (a for a in query if self.is_allocation_exposed(a))

        return self.availability_by_allocations(allocations)

    def availability_by_day(
        self,
        start: datetime,
        end: datetime,
        resources: Collection[UUID]
    ) -> dict[date, tuple[float, set[UUID]]]:
        """Availability by range with a twist. Instead of returning a grand
        total, a dictionary is returned with each day in the range as key and
        a tuple of availability and the resources counted for that day.

        WARNING, this function should run as linearly as possible as a lot
        of records might be processed.

        """
        query = self.all_allocations_in_range(start, end)
        query = query.filter(Allocation.mirror_of.in_(resources))
        query = query.options(joinedload(Allocation.reserved_slots))
        query = query.order_by(Allocation._start)

        group = groupby(query, key=lambda a: a._start.date())
        days = {}

        for day, allocations in group:

            exposed = []
            members = set()

            for a in (a for a in allocations if self.is_allocation_exposed(a)):
                members.add(a.mirror_of)
                exposed.append(a)

            if not exposed:
                continue

            total = self.availability_by_allocations(exposed)

            days[day] = (total, members)

        return days

    def reservations_by_session(
        self,
        session_id: UUID | None
    ) -> Query[Reservation]:

        # be sure to not query for all reservations. since a query should be
        # returned in any case we just use an impossible clause

        # this is mainly a security feature
        if not session_id:
            log.warn('empty session id')
            return self.session.query(Reservation).filter(text('0=1'))

        query = self.session.query(Reservation)
        query = query.filter(Reservation.session_id == session_id)
        query = query.order_by(Reservation.created)

        return query

    def confirm_reservations_for_session(
        self,
        session_id: UUID,
        token: UUID | None = None
    ) -> None:
        """ Confirms all reservations of the given session id. Optionally
        confirms only the reservations with the given token. All if None.

        """

        assert session_id

        res_query = self.reservations_by_session(session_id)

        if token:
            res_query = res_query.filter(Reservation.token == token)

        reservations = res_query.all()

        if not reservations:
            raise errors.NoReservationsToConfirm

        for reservation in reservations:
            reservation.session_id = None

        events.on_reservations_confirmed(
            self.context, reservations, session_id
        )

    def remove_reservation_from_session(
        self,
        session_id: UUID,
        token: UUID
    ) -> None:
        """ Removes the reservation with the given session_id and token. """

        assert token and session_id

        query = self.reservations_by_session(session_id)
        query = query.filter(Reservation.token == token)

        reservation = query.one()
        self.session.delete(reservation)

        # if we get here the token must be valid, we should then check if the
        # token is used in the reserved slots, because with autoapproval these
        # slots may be created straight away.

        slots = self.session.query(ReservedSlot).filter(
            ReservedSlot.reservation_token == token
        ).filter(ReservedSlot.source_type == 'reservation')

        slots.delete('fetch')

        # we also update the timestamp of existing reservations within
        # the same session to ensure that we account for the user's activity
        # properly during the session expiration cronjob. Otherwise it is
        # possible that a user removes the latest reservations only to see
        # the rest of them vanish because his older reservations were
        # already old enough to be counted as expired.

        query = self.session.query(Reservation)
        query = query.filter(Reservation.session_id == session_id)

        query.update({'modified': sedate.utcnow()})

    def find_expired_reservation_sessions(
        self,
        expiration_date: datetime | None
    ) -> list[UUID]:
        """ Goes through all reservations and returns the session ids of the
        unconfirmed ones which are older than the given expiration date.
        By default the expiration date is now - 15 minutes.

        Note that this method goes through ALL RESERVATIONS OF THE CURRENT
        SESSION. This is NOT limited to a specific context or scheduler.

        """

        expiration_date = expiration_date or (
            sedate.utcnow() - timedelta(minutes=15)
        )

        # first get the session ids which are expired
        query: Query[tuple[UUID, datetime, datetime | None]]
        query = self.session.query(  # type: ignore[assignment]
            Reservation.session_id,
            func.max(Reservation.created),
            func.max(Reservation.modified)
        )
        query = query.group_by(Reservation.session_id)

        query = query.filter(Reservation.session_id.isnot(None))

        # only pending reservations are considered
        query = query.filter(Reservation.status == 'pending')

        # the idea is to remove all reservations belonging to sessions whose
        # latest update is expired - either delete the whole session or let
        # all of it be
        return [
            session_id
            for session_id, created, modified in query
            if max(created, modified or created) < expiration_date
        ]

    def remove_expired_reservation_sessions(
        self,
        expiration_date: datetime | None = None
    ) -> list[UUID]:
        """ Removes all reservations which have an expired session id.
        By default the expiration date is now - 15 minutes.

        See :func:`find_expired_reservation_sessions`

        Note that this method goes through ALL RESERVATIONS OF THE CURRENT
        SESSION. This is NOT limited to a specific context or scheduler.

        """

        expired_sessions = self.find_expired_reservation_sessions(
            expiration_date
        )

        # remove those session ids
        if expired_sessions:
            reservations = self.session.query(Reservation)
            reservations = reservations.filter(
                Reservation.session_id.in_(expired_sessions)
            )

            slots = self.session.query(ReservedSlot)
            slots = slots.filter(
                ReservedSlot.reservation_token.in_(
                    reservations.with_entities(Reservation.token)
                )
            )
            slots = slots.filter(ReservedSlot.source_type == 'reservation')

            slots.delete('fetch')
            reservations.delete('fetch')

        return expired_sessions
