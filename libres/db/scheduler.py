from datetime import datetime, timedelta

from libres.context.core import ContextServicesMixin
from libres.context.session import serialized, Serializable
from libres.db.models import ORMBase, Allocation, ReservedSlot, Reservation
from libres.db.queries import Queries
from libres.modules import calendar
from libres.modules import compat
from libres.modules import errors
from libres.modules import events
from libres.modules import rasterizer
from libres.modules import utils

from sqlalchemy.orm import exc
from sqlalchemy.sql import and_, not_

from uuid import uuid4 as new_uuid


missing = object()


class Scheduler(Serializable, ContextServicesMixin):
    """ The Scheduler is responsible for talking to the backend of the given
    context to create reservations. It is the main part of the API.
    """

    def __init__(self, context, name, timezone):
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

        assert isinstance(timezone, compat.string_types)

        self.context = context
        self.queries = Queries(context)

        self.name = name
        self.timezone = timezone

    def clone(self):
        """ Clones the scheduler. The result will be a new scheduler using the
        same context, name, settings and attributes.

        """

        return Scheduler(self.context, self.name, self.timezone)

    @property
    def resource(self):
        """ The resource that belongs to this scheduler. The resource is
        a uuid created from the name and context of this scheduler, based
        on the namespace uuid defined in :ref:`settings.uuid_namespace`

        """
        return self.generate_uuid(self.name)

    def prepare_date(self, date):
        return calendar.standardize_date(date, self.timezone)

    def prepare_dates(self, dates):
        return [
            (
                calendar.standardize_date(s, self.timezone),
                calendar.standardize_date(e, self.timezone)
            ) for s, e in utils.pairs(dates)
        ]

    def prepare_range(self, start, end):
        return (
            calendar.standardize_date(start, self.timezone),
            calendar.standardize_date(end, self.timezone)
        )

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

    @serialized
    def extinguish_managed_records(self):
        """ WARNING:
        Completely removes any trace of the records managed by this scheduler.
        That means all reservations, reserved slots and allocations!

        """
        self.managed_reservations().delete('fetch')
        self.managed_reserved_slots().delete('fetch')
        self.managed_allocations().delete('fetch')

    def allocation_by_id(self, id):
        query = self.managed_allocations()
        query = query.filter(Allocation.mirror_of == self.resource)
        query = query.filter(Allocation.id == id)
        return query.one()

    def allocations_by_ids(self, ids):
        query = self.managed_allocations()
        query = query.filter(Allocation.id.in_(ids))
        query = query.order_by(Allocation._start)
        return query

    def allocations_by_group(self, group, masters_only=True):
        return self.allocations_by_groups([group], masters_only=masters_only)

    def allocations_by_groups(self, groups, masters_only=True):
        query = self.managed_allocations()
        query = query.filter(Allocation.group.in_(groups))

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

    def allocations_by_reservation(self, token, id=None):
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
        allocations = allocations.filter(Allocation.group.in_(
            groups.subquery()
        ))

        query = self.managed_allocations()
        query = query.join(ReservedSlot)
        query = query.filter(
            ReservedSlot.reservation_token == token
        )
        query = query.filter(
            ReservedSlot.allocation_id.in_(
                allocations.subquery()
            )
        )
        return query

    def allocations_in_range(self, start, end, masters_only=True):
        start, end = self.prepare_range(start, end)

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

    def allocation_mirrors_by_master(self, master):
        return [s for s in master.siblings() if not s.is_master]

    def allocation_dates_by_ids(self, ids, start_time=None, end_time=None):

        for allocation in self.allocations_by_ids(ids).all():

            s = start_time or allocation.display_start().time()
            e = end_time or allocation.display_end().time()

            s, e = allocation.limit_timespan(s, e)

            yield s, e - timedelta(microseconds=1)

    def manual_approval_required(self, ids):
        """ Returns True if any of the allocations require manual approval. """
        query = self.allocations_by_ids(ids)
        query = query.filter(Allocation.approve_manually == True)

        return query.first() and True or False

    @serialized
    def allocate(
        self,
        dates,
        quota=None,
        quota_limit=0,
        partly_available=False,
        grouped=False,
        approve_manually=False,
        whole_day=False,
        data=None,
        raster=rasterizer.MIN_RASTER
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

        Note that grouped allocations with only one date-pair are equal
        to ungrouped-allocations. Allocations are only grouped if there are
        multiple allocations.

        The master is the first allocation to be created. The mirrors copies of
        that allocation. See Scheduler.__doc__

        """
        dates = self.prepare_dates(dates)

        group = new_uuid()
        quota = quota or 1

        # This is mostly for historic reasons - it's unclear if the current
        # code could really handle it..
        if partly_available and grouped:
            raise errors.InvalidAllocationError

        # the whole day option results in the dates being aligned to
        # the beginning of the day / end of it -> not timezone aware!
        if whole_day:
            for ix, (start, end) in enumerate(dates):
                dates[ix] = calendar.align_range_to_day(
                    start, end, self.timezone
                )

        # Ensure that the list of dates contains no overlaps inside
        rasterized_dates = [
            rasterizer.rasterize_span(s, e, raster) for s, e in dates
        ]

        for start, end in rasterized_dates:
            if calendar.count_overlaps(rasterized_dates, start, end) > 1:
                raise errors.InvalidAllocationError

        # Make sure that this span does not overlap another master
        for start, end in rasterized_dates:
            existing = self.allocations_in_range(start, end).first()

            if existing:
                raise errors.OverlappingAllocationError(start, end, existing)

        # Write the master allocations
        allocations = []
        for start, end in dates:
            allocation = Allocation()
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

        events.on_allocations_added(self.context, allocations)

        return allocations

    @serialized
    def change_quota(self, master, new_quota):
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

        assert new_quota > 0, "Quota must be greater than 0"

        if new_quota == master.quota:
            return

        if new_quota > master.quota:
            master.quota = new_quota
            return

        # Make sure that the quota can be decreased
        mirrors = self.allocation_mirrors_by_master(master)
        allocations = [master] + mirrors

        free_allocations = [a for a in allocations if a.is_available()]

        required = master.quota - new_quota
        if len(free_allocations) < required:
            raise errors.AffectedReservationError(None)

        # get a map pointing from the existing uuid to the newly assigned uuid
        reordered = self.reordered_keylist(allocations, new_quota)

        # unused keys are the ones not present in the newly assignd uuid list
        unused = set(reordered.keys()) - set(reordered.values()) - set((None,))

        # get a map for resource_uuid -> allocation.id
        ids = dict(((a.resource, a.id) for a in allocations))

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

    def reordered_keylist(self, allocations, new_quota):
        """ Creates the map for the keylist reorganzation.

        Each key of the returned dictionary is a resource uuid pointing to the
        resource uuid it should be moved to. If the allocation should not be
        moved they key-value is None.

        """
        masters = [a for a in allocations if a.is_master]
        assert(len(masters) == 1)

        master = masters[0]
        allocations = dict(((a.resource, a) for a in allocations))

        # generate the keylist (the allocation resources may be unordered)
        keylist = [master.resource]
        keylist.extend(utils.generate_uuids(master.resource, master.quota))

        # prefill the map
        reordered = dict(((k, None) for k in keylist))

        # each free allocation increases the offset by which the next key
        # for a non-free allocation is acquired
        offset = 0
        for ix, key in enumerate(keylist):
            if allocations[key].is_available():
                offset += 1
            else:
                reordered[key] = keylist[ix - offset]

        return reordered

    def availability(self, start=None, end=None):
        """Goes through all allocations and sums up the availability."""

        start = start if start else calendar.mindatetime
        end = end if end else calendar.maxdatetime

        start, end = self.prepare_range(start, end)

        return self.queries.availability_by_range(start, end, [self.resource])

    @serialized
    def move_allocation(
            self, master_id, new_start=None, new_end=None,
            group=None, new_quota=None, approve_manually=None,
            quota_limit=0, whole_day=None, data=missing):

        assert master_id
        assert any([new_start and new_end, group, new_quota])

        new_start = self.prepare_date(new_start)
        new_end = self.prepare_date(new_end)

        # Find allocation
        master = self.allocation_by_id(master_id)
        mirrors = self.allocation_mirrors_by_master(master)

        changing = [master] + mirrors
        ids = [c.id for c in changing]

        assert master.timezone == self.timezone, """
            You are trying to move an allocation that was created with a
            different timezone. This is currently unsupported. See
            Scheduler.__init__ -> timezone
        """

        assert(group or master.group)

        # Simulate the new allocation
        new_start = new_start or master.start
        new_end = new_end or master.end

        if whole_day:
            new_start, new_end = calendar.align_range_to_day(
                new_start, new_end, self.timezone
            )

        new = Allocation(
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

                    if change.is_master and \
                            change.pending_reservations.count():
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

    @serialized
    def remove_allocation(self, id=None, groups=None):
        if id:
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

    @serialized
    def reserve(
        self,
        email,
        dates=None,
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

        email = email.strip()

        if not self.validate_email(email):
            raise errors.InvalidEmailAddress

        if group:
            dates = self.allocation_dates_by_group(group)

        dates = self.prepare_dates(dates)

        # First, the request is checked for saneness. If any requested
        # date cannot be reserved the request as a whole fails.
        for start, end in dates:

            # are the parameters valid?
            if abs((end - start).days) >= 1:
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

                if allocation.quota_limit > 0:
                    if allocation.quota_limit < quota:
                        raise errors.QuotaOverLimit

                if allocation.quota < quota:
                    raise errors.QuotaImpossible

                if quota < 1:
                    raise errors.InvalidQuota

        # ok, we're good to go
        token = new_uuid()
        reservations = []

        # groups are reserved by group-identifier - so all members of a group
        # or none of them. As such there's no start / end date which is defined
        # implicitly by the allocation
        def new_reservations_by_group(group):
            if group:
                reservation = Reservation()
                reservation.token = token
                reservation.target = group
                reservation.status = u'pending'
                reservation.target_type = u'group'
                reservation.resource = self.resource
                reservation.data = data
                reservation.session_id = session_id
                reservation.email = email.strip()
                reservation.quota = quota

                yield reservation

        # all other reservations are reserved by start/end date
        def new_reservations_by_dates(dates):
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

                        # I really want to use 'yield from'. Python 3 ftw!
                        for r in new_reservations_by_group(allocation.group):
                            yield r
                    else:
                        reservation = Reservation()
                        reservation.token = token
                        reservation.start, reservation.end\
                            = rasterizer.rasterize_span(
                                start, end, allocation.raster
                            )
                        reservation.timezone = allocation.timezone
                        reservation.target = allocation.group
                        reservation.status = u'pending'
                        reservation.target_type = u'allocation'
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

        for reservation in reservations:
            self.session.add(reservation)

        events.on_reservations_made(self.context, reservations)

        return token

    @serialized
    def _approve_reservation_record(self, reservation):
        # write out the slots
        slots_to_reserve = []

        if reservation.target_type == u'group':
            dates = self.allocation_dates_by_group(reservation.target)
        else:
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

        reservation.status = u'approved'

        if not slots_to_reserve:
            raise errors.NotReservableError

        return slots_to_reserve

    @serialized
    def approve_reservations(self, token):
        """ This function approves an existing reservation and writes the
        reserved slots accordingly.

        Returns a list with the reserved slots.

        """

        slots_to_reserve = []

        reservations = self.reservations_by_token(token).all()

        for reservation in reservations:
            slots_to_reserve.extend(
                self._approve_reservation_record(reservation)
            )

        events.on_reservations_approved(self.context, reservations)

        return slots_to_reserve

    @serialized
    def deny_reservation(self, token):
        """ Denies a pending reservation, removing it from the records and
        sending an email to the reservee.

        """

        query = self.reservations_by_token(token)
        query = query.filter(Reservation.status == u'pending')

        reservations = query.all()

        query.delete()

        events.on_reservations_denied(self.context, reservations)

    @serialized
    def remove_reservation(self, token, id=None):
        """ Removes all reserved slots of the given reservation token.

        Note that removing a reservation does not let the reservee know that
        his reservation has been removed.

        If you want to let the reservee know what happened,
        use revoke_reservation.

        The id is optional. If given, only the reservation with the given
        token AND id is removed.

        """

        slots = self.reserved_slots_by_reservation(token, id)

        for slot in slots:
            self.session.delete(slot)

        reservations = self.reservations_by_token(token, id)
        reservations.delete('fetch')

        events.on_reservations_removed(self.context, reservations)

    @serialized
    def change_email(self, token, new_email):

        for reservation in self.reservations_by_token(token).all():
            reservation.email = new_email

    @serialized
    def change_reservation_data(self, token, data):

        for reservation in self.reservations_by_token(token).all():
            reservation.data = data

    @serialized
    def change_reservation_time_candidates(self, tokens=None):
        """ Returns the reservations that fullfill the restrictions
        imposed by change_reservation_time.

        Pass a list of reservation tokens to further limit the results.

        """

        query = self.managed_reservations()
        query = query.filter(Reservation.status == 'approved')
        query = query.filter(Reservation.target_type == 'allocation')

        groups = self.managed_allocations().with_entities(Allocation.group)
        groups = groups.filter(Allocation.partly_available == True)

        query = query.filter(Reservation.target.in_(groups.subquery()))

        if tokens:
            query = query.filter(Reservation.token.in_(tokens))

        return query

    @serialized
    def change_reservation_time(self, token, id, new_start, new_end):
        """ Allows to change the timespan of a reservation under certain
        conditions:

        - The new timespan must be reservable inside the existing allocation.
          (So you cannot use this method to reserve another allocation)
        - The referenced allocation must not be in a group.
        - The referenced allocation must be partly available.
        - The referenced reservation must be approved

        There is really only one usecase that this function works for:

        The user wants to change the timespan of a reservation in a meeting
        room kind of setup where you have lots of partly-available
        allocations.

        Returns True if a change was made.

        Just like revoke_reservation, this function raises an event which
        includes a send_email flag and a reason which may be used to inform
        the user of the changes to his reservation.

        """

        # check for the reservation first as the allocation won't exist
        # if the reservation has not been approved yet
        assert new_start and new_end

        new_start = self.prepare_date(new_start)
        new_end = self.prepare_date(new_end)

        existing_reservation = self.reservations_by_token(token, id).one()

        assert existing_reservation.status == 'approved', """
            Reservation must be approved.
        """

        # if there's nothing to change, do not change
        if existing_reservation.start == new_start:
            if existing_reservation.end == new_end:
                return False
            if existing_reservation.end == new_end - timedelta(microseconds=1):
                return False

        # will return raise a MultipleResultsFound exception if this is a group
        allocation = self.allocations_by_reservation(token, id).one()

        assert allocation.partly_available, """
            Allocation must be partly available.
        """

        if not allocation.contains(new_start, new_end):
            raise errors.TimerangeTooLong()

        reservation_arguments = dict(
            email=existing_reservation.email,
            dates=(new_start, new_end),
            data=existing_reservation.data,
            quota=existing_reservation.quota
        )

        old_start = existing_reservation.display_start()
        old_end = existing_reservation.display_end()

        with self.begin_nested():
            self.remove_reservation(token, id)

            new_token = self.reserve(**reservation_arguments)
            new_reservation = self.reservations_by_token(new_token).one()
            new_reservation.id = id
            new_reservation.token = token

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

        return True

    def search_allocations(
        self, start, end,
        days=None,
        minspots=0,
        available_only=False,
        whole_day='any',
        groups='any',
        strict=False
    ):
        """ Search allocations using a number of options. The date is split
        into date/time. All allocations between start and end date within
        the given time (on each day) are included.

        For example, start=01.01.2012 12:00 end=31.01.2012 14:00 will include
        all allocaitons in January 2012 which OVERLAP the given times. So an
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

        :include_groups:
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

        start, end = self.prepare_range(start, end)

        assert whole_day in ('yes', 'no', 'any')
        assert groups in ('yes', 'no', 'any')

        if days:
            days_map = {
                'mo': 0,
                'tu': 1,
                'we': 2,
                'th': 3,
                'fr': 4,
                'sa': 5,
                'su': 6
            }

            # get the day from the map - if impossible take the verbatim value
            # this allows for using strings or integers
            days = set(days_map.get(day, day) for day in days)

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

            s = calendar.replace_timezone(s, allocation.start.tzname())
            e = calendar.replace_timezone(e, allocation.start.tzname())

            if not allocation.overlaps(s, e):
                continue

            if days:
                if allocation.start.weekday() not in days:
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
            if minspots:
                if allocation.quota_limit > 0:
                    if allocation.quota_limit < minspots:
                        continue

            if available_only:
                if not allocation.find_spot(s, e):
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
                allocation.is_extra_result = True
                allocations.append(allocation)

            allocations.sort(key=lambda a: a._start)

        return allocations

    def free_allocations_count(self, master_allocation, start, end):
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

    def reservation_targets(self, start, end):
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

    def reserved_slots_by_reservation(self, token, id=None):
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
            ids = self.allocations_by_reservation(token, id)
            ids = ids.with_entities(Allocation.id)
            return query.filter(
                ReservedSlot.allocation_id.in_(ids.subquery())
            )

    def reservations_by_group(self, group):
        tokens = self.managed_reservations().with_entities(Reservation.token)
        tokens = tokens.filter(Reservation.target == group)

        return self.managed_reservations().filter(
            Reservation.token.in_(
                tokens.subquery()
            )
        )

    def reservations_by_allocation(self, allocation_id):
        master = self.allocation_by_id(allocation_id)

        return self.reservations_by_group(master.group)

    def reservations_by_token(self, token, id=None):
        query = self.managed_reservations()
        query = query.filter(Reservation.token == token)

        if id:
            query = query.filter(Reservation.id == id)

        try:
            query.first()
        except exc.NoResultFound:
            raise errors.InvalidReservationToken

        return query
