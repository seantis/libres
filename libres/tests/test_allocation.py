import pytest

from datetime import datetime, time
from libres.db.models import Allocation
from libres.modules import errors
from pytz import utc
from sqlalchemy.exc import IntegrityError
from uuid import uuid4 as new_uuid


def test_add_allocation(scheduler):

    allocation = Allocation(raster=15, resource=scheduler.resource)
    allocation.start = datetime(2011, 1, 1, 15, tzinfo=utc)
    allocation.end = datetime(2011, 1, 1, 15, 59, tzinfo=utc)
    allocation.group = new_uuid().hex
    allocation.mirror_of = scheduler.resource

    scheduler.session.add(allocation)
    scheduler.commit()

    assert scheduler.session.query(Allocation).count() == 1


def test_add_invalid_allocation(scheduler):
    scheduler.session.add(Allocation(raster=15))

    with pytest.raises(IntegrityError):
        scheduler.commit()


def test_get_master(scheduler):
    dates = [
        (datetime(2015, 2, 6, 12), datetime(2015, 2, 6, 13)),
        (datetime(2015, 2, 7, 12), datetime(2015, 2, 7, 13))
    ]

    allocations = scheduler.allocate(dates[:1])
    assert allocations[0].get_master() is allocations[0]

    allocations = scheduler.allocate(dates[1:], quota=2)
    assert allocations[0].get_master() is allocations[0]

    # the siblings must exist in the database for the query in get_master
    siblings = allocations[0].siblings()
    scheduler.session.add(siblings[1])
    scheduler.commit()

    assert siblings[1].get_master() is allocations[0]
    assert siblings[1].get_master().id == allocations[0].id


def test_imaginary_siblings(scheduler):
    dates = [(datetime(2015, 2, 6, 12), datetime(2015, 2, 6, 13))]
    allocations = scheduler.allocate(dates=dates, quota=2)

    assert len(allocations) == 1
    assert len(allocations[0].siblings()) == 2
    assert len(allocations[0].siblings(imaginary=False)) == 1

    imaginary_allocation = allocations[0].siblings()[1]

    with pytest.raises(AssertionError):
        # we can't get a list of non-imaginary siblings from an imaginary one
        imaginary_allocation.siblings(imaginary=False)


def test_date_functions(scheduler):
    allocation = Allocation(raster=60, resource=scheduler.resource)
    allocation.timezone = 'UTC'
    allocation.start = datetime(2011, 1, 1, 12, 30, tzinfo=utc)
    allocation.end = datetime(2011, 1, 1, 14, 00, tzinfo=utc)

    assert allocation.start.hour == 12
    assert allocation.start.minute == 0
    assert allocation.end.hour == 13
    assert allocation.end.minute == 59

    start = datetime(2011, 1, 1, 11, 00)
    end = datetime(2011, 1, 1, 12, 5)

    assert allocation.overlaps(start, end)
    assert not allocation.contains(start, end)

    start = datetime(2011, 1, 1, 13, 00)
    end = datetime(2011, 1, 1, 15, 00)

    assert allocation.overlaps(start, end)
    assert not allocation.contains(start, end)


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


def test_separate_allocation(scheduler):

    # allocations which are partly available are never in a group
    # (some code, for example allocation.is_separarate, depends on that)
    assert Allocation(partly_available=True).is_separate

    dates = [
        (datetime(2015, 2, 6, 10), datetime(2015, 2, 6, 11)),
        (datetime(2015, 2, 7, 10), datetime(2015, 2, 7, 11))
    ]

    # which is why this won't work
    with pytest.raises(errors.InvalidAllocationError):
        scheduler.allocate(dates=dates, grouped=True, partly_available=True)

    # though this will
    allocations = scheduler.allocate(dates=dates, grouped=True)
    assert not any(a.is_separate for a in allocations)

    # at last, try an allocation that is not in a group, but requires a query
    # check to get that information

    dates = [
        (datetime(2015, 2, 8, 10), datetime(2015, 2, 8, 11))
    ]

    allocations = scheduler.allocate(dates=dates, partly_available=False)
    assert allocations[0].is_separate


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
