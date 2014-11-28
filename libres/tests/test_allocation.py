import pytest

from datetime import datetime, time
from libres.db.models import Allocation
from pytz import utc
from sqlalchemy.exc import IntegrityError
from uuid import uuid4 as new_uuid


def test_add_allocation(scheduler):

    allocation = Allocation(raster=15, resource=scheduler.resource)
    allocation.start = datetime(2011, 1, 1, 15, tzinfo=utc)
    allocation.end = datetime(2011, 1, 1, 15, 59, tzinfo=utc)
    allocation.group = new_uuid().hex
    allocation.mirror_of = scheduler.resource

    scheduler.context.serial_session.add(allocation)
    scheduler.commit()

    assert scheduler.session.query(Allocation).count() == 1


def test_add_invalid_allocation(scheduler):
    scheduler.context.serial_session.add(Allocation(raster=15))

    with pytest.raises(IntegrityError):
        scheduler.commit()


def test_whole_day():
    allocation = Allocation(
        raster=15, resource=new_uuid(), timezone='Europe/Zurich'
    )

    # the whole-day is relative to the allocation's timezone
    allocation.start = datetime(2013, 1, 1, 23, 0, tzinfo=utc)
    allocation.end = datetime(2013, 1, 2, 23, 0, tzinfo=utc)

    assert allocation.whole_day

    allocation.start = datetime(2013, 1, 1, 23, 0, tzinfo=utc)
    allocation.end = datetime(2013, 1, 2, 22, 59, 59, 999999, tzinfo=utc)

    assert allocation.whole_day

    allocation.start = datetime(2013, 1, 1, 23, 0, tzinfo=utc)
    allocation.end = datetime(2013, 1, 2, 22, 59, 59, 999999, tzinfo=utc)

    assert allocation.whole_day

    allocation.start = datetime(2013, 1, 1, 15, 0, tzinfo=utc)
    allocation.end = datetime(2013, 1, 1, 0, 0, tzinfo=utc)

    with pytest.raises(AssertionError):
        allocation.whole_day


def test_limit_timespan():

    # if not partly availabe the limit is always the same
    allocation = Allocation(
        raster=15, resource=new_uuid(), partly_available=False, timezone='UTC'
    )

    allocation.start = datetime(2014, 1, 1, 8, 0, tzinfo=utc)
    allocation.end = datetime(2014, 1, 1, 9, 0, tzinfo=utc)

    assert allocation.limit_timespan(time(8, 0), time(9, 0)) == (
        allocation.display_start(), allocation.display_end()
    )

    assert allocation.limit_timespan(time(7, 0), time(10, 0)) == (
        allocation.display_start(), allocation.display_end()
    )

    # if partly available, more complex things happen
    allocation = Allocation(
        raster=15, resource=new_uuid(), partly_available=True, timezone='UTC'
    )

    allocation.start = datetime(2014, 1, 1, 8, 0, tzinfo=utc)
    allocation.end = datetime(2014, 1, 1, 9, 0, tzinfo=utc)

    assert allocation.limit_timespan(time(8, 0), time(9, 0)) == (
        allocation.display_start(), allocation.display_end()
    )

    assert allocation.limit_timespan(time(7, 0), time(10, 0)) == (
        allocation.display_start(), allocation.display_end()
    )

    assert allocation.limit_timespan(time(8, 30), time(10, 0)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 1, 9, 0, tzinfo=utc)
    )

    assert allocation.limit_timespan(time(8, 30), time(8, 40)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 1, 8, 45, tzinfo=utc)
    )

    assert allocation.limit_timespan(time(8, 30), time(0, 0)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 1, 9, 0, tzinfo=utc)
    )

    # no problems should arise if whole-day allocations are used
    allocation.start = datetime(2014, 1, 1, 0, 0, tzinfo=utc)
    allocation.end = datetime(2014, 1, 2, 0, 0, tzinfo=utc)

    assert allocation.whole_day

    assert allocation.limit_timespan(time(0, 0), time(23, 59)) == (
        allocation.display_start(), allocation.display_end()
    )

    assert allocation.limit_timespan(time(0, 0), time(0, 0)) == (
        datetime(2014, 1, 1, 0, 0, tzinfo=utc),
        datetime(2014, 1, 1, 0, 0, tzinfo=utc)
    )

    assert allocation.limit_timespan(time(8, 30), time(10, 0)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 1, 10, 0, tzinfo=utc)
    )

    assert allocation.limit_timespan(time(8, 30), time(8, 40)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 1, 8, 45, tzinfo=utc)
    )

    assert allocation.limit_timespan(time(8, 30), time(0, 0)) == (
        datetime(2014, 1, 1, 8, 30, tzinfo=utc),
        datetime(2014, 1, 2, 0, 0, tzinfo=utc)
    )
