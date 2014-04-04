import arrow

from uuid import uuid4 as new_uuid
from uuid import uuid5 as new_namespace_uuid

from sqlalchemy.orm import exc

from libres.modules import calendar
from libres.modules import errors
from libres.modules import raster
from libres.modules import utils
from libres.modules import events

from libres.context.session import serialized
from libres.context.accessor import ContextAccessor

from libres.db.models import ORMBase, Allocation, ReservedSlot, Reservation
from libres.db.queries import Queries


class Scheduler(object):
    """ The Scheduler is responsible for talking to the backend of the given
    context to create reservations. It is the main part of the API.
    """

    def __init__(self, context, name, settings={}):
        """ Initializeds a new Scheduler instance.

        :context:
            The name of the context this scheduler should operate on.
            If the context does not yet exist, it will be created.

        :name:
            The name of the Scheduler. The context and name of the scheduler
            are used to generate the resource uuid in the database. To
            access the data you generated with a scheduler use the same context
            and name together.

        """

        self.context = ContextAccessor(context, autocreate=True)
        self.queries = Queries(context)

        self.name = name

        for name, value in settings.items():
            self.context.set_config(name, value)

    @property
    def session(self):
        """ Returns the current session. This can be the read-only or the
        serialized session, depending on where it is called from.

        """
        return self.context.session

    @property
    def resource(self):
        """ The resource that belongs to this scheduler. The resource is
        a uuid created from the name and context of this scheduler, based
        on the namespace uuid defined in :ref:`settings.uuid_namespace`

        """
        return new_namespace_uuid(
            self.context.get_config('settings.uuid_namespace'),
            '/'.join((self.name, self.context.name))
        )

    def begin(self):
        return self.context.serial_session.begin(subtransactions=True)

    def commit(self):
        return self.context.serial_session.commit()

    def rollback(self):
        return self.context.serial_session.rollback()

    @serialized
    def setup_database(self):
        ORMBase.metadata.create_all(self.session.bind)

    def managed_allocations(self):
        """ The allocations managed by this scheduler / resource. """
        query = self.session.query(Allocation)
        query = query.filter(Allocation.mirror_of == self.resource)

        return query

    def managed_reserved_slots(self):
        """ The reserved_slots managed by this scheduler / resource. """
        uuids = self.managed_allocations().with_entities(Allocation.resource)

        query = self.session.query(ReservedSlot)
        query = query.filter(ReservedSlot.resource.in_(uuids))

        return query

    def managed_reservations(self):
        """ The reservations managed by this scheduler / resource. """
        query = self.session.query(Reservation)
        query = query.filter(Reservation.resource == self.resource)

        return query

    def allocation_by_id(self, id):
        query = self.managed_allocations()
        query = query.filter(Allocation.mirror_of == self.resource)
        query = query.filter(Allocation.id == id)
        return query.one()

    def allocations_by_group(self, group, masters_only=True):
        query = self.managed_allocations()
        query = query.filter(Allocation.group == group)

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

    def allocations_by_reservation(self, reservation_token):
        """ Returns the allocations for the reservation if it was *approved*,
        pending reservations return nothing. If you need to get the allocation
        a pending reservation might be targeting, use _target_allocations
        in model.reservation.

        """
        query = self.managed_allocations()
        query = query.join(ReservedSlot)
        query = query.filter(
            ReservedSlot.reservation_token == reservation_token
        )
        return query

    def allocations_in_range(self, start, end, masters_only=True):
        query = self.managed_allocations()
        query = self.queries.allocations_in_range(query, start, end)

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

    def allocation_by_date(self, start, end):
        query = self.allocations_in_range(start, end)
        return query.one()

    def allocation_dates_by_group(self, group):
        query = self.allocations_by_group(group)
        query = query.with_entities(Allocation._start, Allocation._end)

        return query.all()

    def reservation_by_token(self, token):
        query = self.managed_reservations()
        query = query.filter(Reservation.token == token)

        try:
            query.one()
        except exc.NoResultFound:
            raise errors.InvalidReservationToken
        except exc.MultipleResultsFound:
            raise NotImplementedError

        return query

    def normalize_dates(self, dates, timezone):
        dates = list(utils.pairs(dates))

        # the dates are expected to be given local to the timezone, but
        # they are converted to utc for storage
        for ix, (start, end) in enumerate(dates):

            start = arrow.get(start).replace(tzinfo=timezone).to('UTC')
            end = arrow.get(end).replace(tzinfo=timezone).to('UTC')

            # while we're at it let's check the dates
            if start == end:
                raise errors.DatesMayNotBeEqualError

            dates[ix] = (start.datetime, end.datetime)

        return dates

    @serialized
    def allocate(
        self,
        dates,
        timezone,
        quota=None,
        quota_limit=0,
        partly_available=False,
        grouped=False,
        approve_manually=True,
        whole_day=False,
        raster_value=raster.MIN_RASTER_VALUE
    ):
        """Allocates a spot in the calendar.

        An allocation defines a timerange which can be reserved. No
        reservations can exist outside of existing allocations. In fact any
        reserved slot will link to an allocation.

        An allocation may be available as a whole (to reserve all or nothing).
        It may also be partly available which means reservations can be made
        for parts of the allocation.

        If an allocation is partly available a raster defines the granularity
        with which a reservation can be made (e.g. a raster of 15min will
        ensure that reservations are at least 15 minutes long and start either
        at :00, :15, :30 or :45)

        The reason for the raster is mainly to ensure that different
        reservations trying to reserve overlapping times need the same keys in
        the reserved_slots table, ensuring integrity at the database level.

        Allocations may have a quota, which determines how many times an
        allocation may be reserved. Quotas are enabled using a master-mirrors
        relationship.

        The master is the first allocation to be created. The mirrors copies of
        that allocation. See Scheduler.__doc__

        """
        dates = self.normalize_dates(dates, timezone)

        group = new_uuid()
        quota = quota or 1

        # the whole day option results in the dates being aligned to
        # the beginning of the day / end of it -> not timezone aware!
        if whole_day:
            for ix, (start, end) in enumerate(dates):
                dates[ix] = calendar.align_range_to_day(start, end, timezone)

        # Ensure that the list of dates contains no overlaps inside
        for start, end in dates:
            if calendar.count_overlaps(dates, start, end) > 1:
                raise errors.InvalidAllocationError

        # Make sure that this span does not overlap another master
        for start, end in dates:
            start, end = raster.rasterize_span(start, end, raster_value)

            existing = self.allocations_in_range(start, end).first()
            if existing:
                raise errors.OverlappingAllocationError(start, end, existing)

        # Write the master allocations
        allocations = []
        for start, end in dates:
            allocation = Allocation()
            allocation.raster = raster_value
            allocation.start = start
            allocation.end = end
            allocation.timezone = timezone
            allocation.resource = self.resource
            allocation.mirror_of = self.resource
            allocation.quota = quota
            allocation.quota_limit = quota_limit
            allocation.partly_available = partly_available
            allocation.approve_manually = approve_manually

            if grouped:
                allocation.group = group
            else:
                allocation.group = new_uuid()

            allocations.append(allocation)

        self.session.add_all(allocations)

        events.on_allocations_add(self.context.name, allocations)

        return allocations

    @serialized
    def reserve(
        self,
        email,
        dates=None,
        timezone=None,
        group=None,
        data=None,
        session_id=None,
        quota=1
    ):
        """ First step of the reservation.

        Seantis.reservation uses a two-step reservation process. The first
        step is reserving what is either an open spot or a place on the
        waiting list.

        The second step is to actually write out the reserved slots, which
        is done by approving an existing reservation.

        Most checks are done in the reserve functions. The approval step
        only fails if there's no open spot.

        This function returns a reservation token which can be used to
        approve the reservation in approve_reservation.

        """

        assert (dates or group) and not (dates and group)
        assert dates and timezone or not dates

        email = email.strip()

        if not self.context.validate_email(email):
            raise errors.InvalidEmailAddress

        if group:
            dates = self.allocation_dates_by_group(group)

        dates = self.normalize_dates(dates, timezone)

        # First, the request is checked for saneness. If any requested
        # date cannot be reserved the request as a whole fails.
        for start, end in dates:

            # are the parameters valid?
            if abs((end - start).days) >= 1:
                raise errors.ReservationTooLong

            if start > end or (end - start).seconds < 5 * 60:
                raise errors.ReservationParametersInvalid

            # can all allocations be reserved?
            for allocation in self.allocations_in_range(start, end):

                # start and end are not rasterized, so we need this check
                if not allocation.overlaps(start, end):
                    continue

                assert allocation.is_master

                # with manual approval the reservation ends up on the
                # waitinglist and does not yet need a spot
                if not allocation.approve_manually:
                    if not self.find_spot(allocation, start, end):
                        raise errors.AlreadyReservedError

                    free = self.free_allocations_count(allocation, start, end)
                    if free < quota:
                        raise errors.AlreadyReservedError

                if allocation.quota_limit > 0:
                    if allocation.quota_limit < quota:
                        raise errors.QuotaOverLimit

                if allocation.quota < quota:
                    raise errors.QuotaImpossible

                if quota < 1:
                    raise errors.InvalidQuota

        # ok, we're good to go
        token = new_uuid()
        found = 0

        # groups are reserved by group-identifier - so all members of a group
        # or none of them. As such there's no start / end date which is defined
        # implicitly by the allocation
        if group:
            found = 1
            reservation = Reservation()
            reservation.token = token
            reservation.target = group
            reservation.status = u'pending'
            reservation.target_type = u'group'
            reservation.resource = self.uuid
            reservation.data = data
            reservation.session_id = session_id
            reservation.email = email
            reservation.quota = quota
            self.session.add(reservation)
        else:
            groups = []

            for start, end in dates:

                for allocation in self.allocations_in_range(start, end):

                    if not allocation.overlaps(start, end):
                        continue

                    found += 1

                    reservation = Reservation()
                    reservation.token = token
                    reservation.start, reservation.end = raster.rasterize_span(
                        start, end, allocation.raster
                    )
                    reservation.timezone = timezone
                    reservation.target = allocation.group
                    reservation.status = u'pending'
                    reservation.target_type = u'allocation'
                    reservation.resource = self.resource
                    reservation.data = data
                    reservation.session_id = session_id
                    reservation.email = email
                    reservation.quota = quota
                    self.session.add(reservation)

                    groups.append(allocation.group)

            # check if no group reservation is made with this request.
            # reserve by group in this case (or make this function
            # do that automatically)
            assert len(groups) == len(set(groups)), \
                'wrongly trying to reserve a group'

        if found:
            events.on_reservation_made(self.context.name, reservation)
        else:
            raise errors.InvalidReservationError

        return token

    @serialized
    def approve_reservation(self, token):
        """ This function approves an existing reservation and writes the
        reserved slots accordingly.

        Returns a list with the reserved slots.

        """

        reservation = self.reservation_by_token(token).one()

        # write out the slots
        slots_to_reserve = []

        if reservation.target_type == u'group':
            dates = self.dates_by_group(reservation.target)
        else:
            dates = ((reservation.start, reservation.end),)

        # the reservation quota is simply implemented by multiplying the
        # dates which are approved

        dates = dates * reservation.quota

        for start, end in dates:

            for allocation in self.reservation_targets(start, end):
                for slot_start, slot_end in allocation.all_slots(start, end):
                    slot = ReservedSlot()
                    slot.start = slot_start
                    slot.end = slot_end
                    slot.resource = allocation.resource
                    slot.reservation_token = token

                    # the slots are written with the allocation
                    allocation.reserved_slots.append(slot)
                    slots_to_reserve.append(slot)

                # the allocation may be a fake one, in which case we
                # must make it realz yo
                if allocation.is_transient:
                    self.session.add(allocation)

        reservation.status = u'approved'

        if not slots_to_reserve:
            raise errors.NotReservableError

        events.on_reservation_approve(self.context.name, reservation)

        return slots_to_reserve

    @serialized
    def deny_reservation(self, token):
        """ Denies a pending reservation. """

        query = self.reservation_by_token(token)
        query.filter(Reservation.status == u'pending')

        reservation = query.one()
        self.session.delete(reservation)

        events.on_reservation_deny(self.context.name, reservation)

    @serialized
    def remove_reservation(self, token):
        """ Removes all reserved slots of the given reservation token. """

        slots = self.reserved_slots_by_reservation(token)

        for slot in slots:
            self.session.delete(slot)

        reservation = self.reservation_by_token(token).one()
        reservation.delete()

        events.on_reservation_remove(self.context.name, reservation)

    @serialized
    def update_reservation_data(self, token, data):

        reservation = self.reservation_by_token(token).one()
        reservation.data = data
