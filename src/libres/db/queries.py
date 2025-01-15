from __future__ import annotations

import logging
import sedate

from datetime import date, datetime, timedelta
from itertools import groupby
from libres.context.core import ContextServicesMixin
from libres.db.models import Allocation, Reservation, ReservedSlot
from libres.modules import errors, events
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import and_, or_


from typing import TypeVar
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Collection
    from collections.abc import Iterable
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
            return self.session.query(Reservation).filter('0=1')

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
        )

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
        query = self.session.query(
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

            slots.delete('fetch')
            reservations.delete('fetch')

        return expired_sessions
