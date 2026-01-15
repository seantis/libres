from __future__ import annotations

import pytest
import sedate

from datetime import datetime, timedelta
from libres.modules import errors
from libres.modules import utils
from sqlalchemy.orm.exc import MultipleResultsFound


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from libres.db.scheduler import Scheduler


def test_move_allocation_with_existing_blocker(
    scheduler: Scheduler
) -> None:

    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 11))]

    allocations = scheduler.allocate(dates)
    scheduler.add_blocker(dates)
    scheduler.commit()

    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            allocations[0].id,
            new_start=datetime(2015, 2, 9, 10),
            new_end=datetime(2015, 2, 9, 12)
        )


def test_move_partly_available_allocation_with_existing_reservation(
    scheduler: Scheduler
) -> None:

    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    allocations = scheduler.allocate(dates, partly_available=True)
    scheduler.add_blocker(dates)
    scheduler.commit()

    # partly available allocations cannot be shrunk smaller if a
    # reservation covers that spot...
    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            allocations[0].id,
            new_start=datetime(2015, 2, 9, 10),
            new_end=datetime(2015, 2, 9, 11)
        )

    # .. but the allocations may be grown
    scheduler.move_allocation(
        allocations[0].id,
        new_start=datetime(2015, 2, 9, 10),
        new_end=datetime(2015, 2, 9, 13)
    )
    scheduler.commit()


def test_blocker_too_short(scheduler: Scheduler) -> None:

    with pytest.raises(errors.ReservationTooShort):
        scheduler.add_blocker(dates=[
            (datetime(2015, 2, 9, 10, 0), datetime(2015, 2, 9, 10, 1)),
        ])


def test_add_blocker(scheduler: Scheduler) -> None:

    start = datetime(2011, 1, 1, 15)
    end = datetime(2011, 1, 1, 16)

    # create an allocation (no need for a commit yet, we won't hit the db again
    # until we check the remaining slots below)
    allocations = scheduler.allocate(
        (start, end), partly_available=True, raster=15
    )

    assert len(allocations) == 1
    allocation = allocations[0]

    # 1 hour / 15 min = 4
    possible_dates = list(allocation.all_slots())
    assert len(possible_dates) == 4

    # block half of the slots
    time = (datetime(2011, 1, 1, 15), datetime(2011, 1, 1, 15, 30))
    blocker, = scheduler.add_blocker(time)

    # commit the changes (or we'll hit the db, which at this point is dirty,
    # resulting in a DirtyReadOnlySession exception)
    scheduler.commit()

    # check the remaining slots
    remaining = allocation.free_slots()
    assert len(remaining) == 2
    assert remaining == possible_dates[2:]

    reserved_slots = scheduler.reserved_slots_by_blocker(blocker.token).all()
    assert len(reserved_slots) == 2

    # try to illegally move the slot
    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            master_id=allocation.id,
            new_start=datetime(2011, 1, 1, 15, 30),
            new_end=datetime(2011, 1, 1, 16),
        )

    assert len(allocation.free_slots()) == 2

    # actually move the slot
    scheduler.move_allocation(
        master_id=allocation.id,
        new_start=datetime(2011, 1, 1, 15),
        new_end=datetime(2011, 1, 1, 15, 30)
    )

    # there should be fewer slots now
    assert len(allocation.free_slots()) == 0

    # remove the reservation
    scheduler.remove_blocker(blocker.token)
    scheduler.session.refresh(allocation)
    assert len(allocation.free_slots()) == 2


def test_change_reason(scheduler: Scheduler) -> None:
    # block multiple allocations
    dates = (
        (datetime(2014, 8, 7, 11, 0), datetime(2014, 8, 7, 12, 0)),
        (datetime(2014, 8, 8, 11, 0), datetime(2014, 8, 8, 12, 0))
    )

    scheduler.allocate(dates)
    blockers = scheduler.add_blocker(dates, reason='mopping')
    assert len(blockers) == 2
    token = blockers[0].token
    assert [b.reason for b in blockers] == ['mopping'] * 2
    scheduler.commit()

    # change the reason and ensure that all blocker records are changed
    scheduler.change_blocker_reason(blockers[0].token, 'cleaning')
    scheduler.commit()
    assert [
        b.reason for b in scheduler.blockers_by_token(token)
    ] == ['cleaning'] * 2


def test_change_blocker_assertions(scheduler: Scheduler) -> None:
    dates: tuple[tuple[datetime, datetime], ...] = (
        (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 17, 0)),
    )

    scheduler.allocate(dates, partly_available=False)
    blocker1, = scheduler.add_blocker(dates)
    scheduler.commit()

    dates = (
        (datetime(2014, 8, 10, 11, 0), datetime(2014, 8, 10, 12, 0)),
        (datetime(2014, 8, 11, 11, 0), datetime(2014, 8, 11, 12, 0)),
    )

    scheduler.allocate(dates, grouped=True)
    blocker2, = scheduler.add_blocker(dates)
    scheduler.commit()

    with pytest.raises(MultipleResultsFound):
        scheduler.change_blocker(
            blocker2.token, blocker2.id, datetime.now(), datetime.now()
        )

    # fail if the dates are outside the allocation
    dates = (
        (datetime(2014, 3, 7, 8, 0), datetime(2014, 3, 7, 17, 0)),
    )

    scheduler.allocate(dates, partly_available=True)
    blocker3, = scheduler.add_blocker(dates)
    scheduler.commit()

    # make sure that the timerange given fits inside the allocation
    with pytest.raises(errors.TimerangeTooLong):
        scheduler.change_blocker(
            blocker3.token, blocker3.id,
            datetime(2014, 3, 7, 7, 0), datetime(2014, 3, 7, 17, 0)
        )

    with pytest.raises(errors.TimerangeTooLong):
        scheduler.change_blocker(
            blocker3.token, blocker3.id,
            datetime(2014, 3, 7, 8, 0), datetime(2014, 3, 7, 17, 1)
        )


def test_change_blocker(scheduler: Scheduler) -> None:
    dates = (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 10, 0))

    scheduler.allocate(dates, partly_available=True)

    token = scheduler.add_blocker(
        (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 9)),
        reason='cleaning'
    )[0].token
    scheduler.commit()

    blocker = scheduler.blockers_by_token(token).one()
    original_id = blocker.id
    assert original_id is not None

    # make sure that no changes are made in these cases
    assert not scheduler.change_blocker(
        token, original_id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 9)
    )

    assert not scheduler.change_blocker(
        token, original_id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 9) - timedelta(microseconds=1)
    )

    # make sure the change is propagated
    scheduler.change_blocker(
        token, original_id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 10)
    )
    scheduler.commit()

    blocker = scheduler.blockers_by_token(token).one()

    assert blocker.start == sedate.standardize_date(
        datetime(2014, 8, 7, 8, 0), scheduler.timezone
    )
    assert blocker.end == sedate.standardize_date(
        datetime(2014, 8, 7, 10, 0) - timedelta(microseconds=1),
        scheduler.timezone
    )

    # the reason must stay the same
    assert blocker.reason == 'cleaning'
    assert blocker.id == original_id
    assert blocker.token == token

    scheduler.change_blocker(
        token, original_id,
        datetime(2014, 8, 7, 9, 0),
        datetime(2014, 8, 7, 10, 0)
    )

    scheduler.add_blocker(
        (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 9))
    )

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.change_blocker(
            token, original_id,
            datetime(2014, 8, 7, 8, 0),
            datetime(2014, 8, 7, 10, 0)
        )


def test_group_add_blocker(scheduler: Scheduler) -> None:
    dates = [
        (datetime(2013, 4, 6, 12, 0), datetime(2013, 4, 6, 16, 0)),
        (datetime(2013, 4, 7, 12, 0), datetime(2013, 4, 7, 16, 0))
    ]

    allocations = scheduler.allocate(
        dates, grouped=True, approve_manually=True, quota=3
    )

    assert len(allocations) == 2

    group = allocations[0].group

    # blocking will use up all the quota
    blocker, = scheduler.add_blocker(group=group)
    scheduler.commit()

    assert blocker.target_allocations().count() == 2
    assert blocker.target_allocations(masters_only=False).count() == 6

    # so trying to block the same thing again will fail
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.add_blocker(group=group)


def test_invalid_block(scheduler: Scheduler) -> None:
    # try to block a spot that doesn't exist
    astart = datetime(2012, 1, 1, 15, 0)
    aend = datetime(2012, 1, 1, 16, 0)
    adates = (astart, aend)

    rstart = datetime(2012, 2, 1, 15, 0)
    rend = datetime(2012, 2, 1, 16, 0)
    rdates = (rstart, rend)

    scheduler.allocate(dates=adates, approve_manually=True)

    with pytest.raises(errors.InvalidReservationError):
        scheduler.add_blocker(rdates)


def test_no_bleed(scheduler: Scheduler) -> None:
    """ Ensures that two allocations close to each other are not mistaken
    when using scheduler.add_blocker. If they do then they bleed over, hence
    the name.

    """
    d1 = (datetime(2011, 1, 1, 15, 0), datetime(2011, 1, 1, 16, 0))
    d2 = (datetime(2011, 1, 1, 16, 0), datetime(2011, 1, 1, 17, 0))

    a1 = scheduler.allocate(d1)[0]
    a2 = scheduler.allocate(d2)[0]

    scheduler.commit()

    assert not a1.overlaps(*d2)
    assert not a2.overlaps(*d1)

    # expect no exceptions
    scheduler.add_blocker(d2)
    scheduler.add_blocker(d1)


def test_group_move_blocked_allocations(scheduler: Scheduler) -> None:
    dates = [
        (datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0)),
        (datetime(2013, 1, 2, 12, 0), datetime(2013, 1, 2, 13, 0))
    ]

    allocations = scheduler.allocate(
        dates, grouped=True, quota=3, approve_manually=True, quota_limit=3
    )
    scheduler.commit()

    for allocation in allocations:
        assert len(allocation.siblings()) == 3

    assert allocations[0].group == allocations[1].group

    # it is possible to move one allocation of a group, but all properties
    # but the date should remain the same

    newstart, newend = (
        datetime(2014, 1, 1, 12, 0), datetime(2014, 1, 1, 13, 0)
    )
    scheduler.move_allocation(
        allocations[0].id, newstart, newend,
        new_quota=2, approve_manually=True, quota_limit=2
    )
    scheduler.commit()

    group_allocations = scheduler.allocations_by_group(
        allocations[0].group).all()
    assert len(group_allocations) == 2

    for a in group_allocations:
        assert a.is_master
        assert a.quota == 2
        assert a.quota_limit == 2

        for allocation in a.siblings():
            # can't check transient allocations for siblings as it requires
            # the session to be set -> this test worked in seantis.reservation
            # because it always operated under one session
            if not allocation.is_transient:
                assert len(allocation.siblings()) == 2

    scheduler.add_blocker(group=allocations[0].group)
    scheduler.commit()

    group_allocations = scheduler.allocations_by_group(
        allocations[0].group).all()
    all = list(utils.flatten([a.siblings() for a in group_allocations]))
    assert scheduler.queries.availability_by_allocations(all) == 0.0

    for a in all:
        assert not a.is_available()

    assert len(all) == 4

    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            allocations[0].id, newstart, newend, new_quota=1
        )


def test_blocker_too_long(scheduler: Scheduler) -> None:
    # ensure that no user can make a blocker for more than 24 hours at
    # a time.

    start = datetime(2011, 1, 1, 15, 0)
    end = start + timedelta(days=1)

    with pytest.raises(errors.ReservationTooLong):
        scheduler.add_blocker((start, end))


def test_partly(scheduler: Scheduler) -> None:
    allocations = scheduler.allocate(
        (
            datetime(2011, 1, 1, 8, 0),
            datetime(2011, 1, 1, 18, 0)
        ),
        partly_available=False,
        approve_manually=False
    )

    assert len(allocations) == 1
    allocation = allocations[0]

    assert len(list(allocation.all_slots())) == 1
    assert len(list(allocation.free_slots())) == 1

    slot = list(allocation.all_slots())[0]
    assert slot[0] == allocation.start
    assert slot[1] == allocation.end

    slot = list(allocation.free_slots())[0]
    assert slot[0] == allocation.start
    assert slot[1] == allocation.end

    scheduler.add_blocker(
        (datetime(2011, 1, 1, 16, 0), datetime(2011, 1, 1, 18, 0))
    )

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.add_blocker(
            (datetime(2011, 1, 1, 8, 0), datetime(2011, 1, 1, 9, 0))
        )


def test_fragmentation(scheduler: Scheduler) -> None:
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)
    daterange = (start, end)

    allocation = scheduler.allocate(daterange, quota=3)[0]
    blocker, = scheduler.add_blocker(daterange)
    scheduler.remove_blocker(blocker.token)
    scheduler.add_blocker(daterange)

    with pytest.raises(errors.AffectedReservationError):
        scheduler.remove_allocation(allocation.id)


def test_allocations_by_blocker(scheduler: Scheduler) -> None:
    start = datetime(2013, 12, 3, 13, 0)
    end = datetime(2013, 12, 3, 15, 0)
    daterange = (start, end)

    allocations = scheduler.allocate(daterange, approve_manually=True)
    token = scheduler.add_blocker(daterange)[0].token
    scheduler.commit()

    assert scheduler.allocations_by_blocker(token).all() == allocations

    # the reverse lookup also returns the same thing
    blocker = scheduler.blockers_by_token(token).one()
    assert blocker.target_allocations().all() == allocations


def test_allocations_by_multiple_blocker(scheduler: Scheduler) -> None:
    ranges = (
        (datetime(2013, 12, 3, 13, 0), datetime(2013, 12, 3, 15, 0)),
        (datetime(2014, 12, 3, 13, 0), datetime(2014, 12, 3, 15, 0))
    )

    allocations = []
    for start, end in ranges:
        allocations.extend(
            scheduler.allocate((start, end), approve_manually=True)
        )

    token = scheduler.add_blocker(ranges)[0].token
    scheduler.commit()

    # we now have multiple reservations pointing to multiple tokens
    # bound together in one reservation token
    assert len(scheduler.allocations_by_blocker(token).all()) == 2

    # which we can limit by reservation id
    blockers = scheduler.managed_blockers().all()

    query = scheduler.allocations_by_blocker(token, blockers[0].id)
    assert query.count() == 1

    query = scheduler.allocations_by_blocker(token, blockers[1].id)
    assert query.count() == 1
