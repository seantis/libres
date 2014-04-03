import arrow

from uuid import uuid4 as new_uuid
from uuid import uuid5 as new_namespace_uuid

from sqlalchemy.sql import and_, or_

from libres.modules import calendar
from libres.modules import errors
from libres.modules import raster
from libres.modules import utils
from libres.modules import events

from libres.models import ORMBase, Allocation
from libres.services.session import serialized
from libres.services.accessor import ContextAccessor


class Scheduler(object):

    def __init__(self, context, name, settings={}):
        self.context = ContextAccessor(context, autocreate=True)
        self.name = name

        for name, value in settings.items():
            self.context.set_config(name, value)

    @property
    def resource(self):
        return new_namespace_uuid(
            self.context.get_config('settings.uuid_namespace'), self.name
        )

    def begin(self):
        return self.context.serial_session.begin(subtransactions=True)

    def commit(self):
        return self.context.serial_session.commit()

    def rollback(self):
        return self.context.serial_session.rollback()

    @property
    def session(self):
        return self.context.session

    @serialized
    def setup_database(self):
        ORMBase.metadata.create_all(self.session.bind)

    def managed_allocations(self):
        """ The allocations managed by this scheduler / resource. """
        query = self.session.query(Allocation)
        query = query.filter(Allocation.mirror_of == self.resource)

        return query

    def allocations_in_range(self, start, end, masters_only=True):
        query = self.managed_allocations()
        query = query.filter(
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

        if masters_only:
            query = query.filter(Allocation.resource == self.resource)

        return query

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
        dates = list(utils.pairs(dates))

        group = new_uuid()
        quota = quota or 1

        # the dates are expected to be given local to the timezone, but
        # they are converted to utc for storage
        for ix, (start, end) in enumerate(dates):

            start = arrow.get(start).replace(tzinfo=timezone).to('UTC')
            end = arrow.get(end).replace(tzinfo=timezone).to('UTC')

            # while we're at it let's check the dates
            if start == end:
                raise errors.DatesMayNotBeEqualError

            dates[ix] = (start.datetime, end.datetime)

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
