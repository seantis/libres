import pytest

from datetime import datetime, timedelta
from libres.modules import calendar, errors, events
from mock import Mock
from sqlalchemy.orm.exc import MultipleResultsFound


def test_transaction(scheduler):

    # begin a transaction
    scheduler.begin()

    # write something in the transaction
    scheduler.allocate(
        (datetime(2014, 4, 4, 14, 0), datetime(2014, 4, 4, 15, 0))
    )

    # rollback the transaction
    scheduler.rollback()

    # nothing should have happened
    assert scheduler.managed_allocations().count() == 0


def test_managed_allocations(scheduler):

    start = datetime(2014, 4, 4, 14, 0)
    end = datetime(2014, 4, 4, 15, 0)

    allocations = scheduler.allocate((start, end))
    assert len(allocations) == 1

    scheduler.commit()

    # create a second scheduler using the same context, but with a different
    # name, which should result in a different set of managed allocations
    s2 = scheduler.clone()
    assert s2.managed_allocations().count() == 1

    s2.name = 'clone'
    assert s2.managed_allocations().count() == 0

    s2.allocate((start, end))
    s2.commit()

    assert s2.managed_allocations().count() == 1

    assert scheduler.managed_allocations().count() == 1
    assert s2.managed_allocations().count() == 1


def test_reserve(scheduler):

    start = datetime(2011, 1, 1, 15)
    end = datetime(2011, 1, 1, 16)

    # create an allocation (no need for a commit yet, we won't hit the db again
    # until we check the remaining slots below)
    allocations = scheduler.allocate(
        (start, end), partly_available=True, raster_value=15
    )

    assert len(allocations) == 1
    allocation = allocations[0]

    # 1 hour / 15 min = 4
    possible_dates = list(allocation.all_slots())
    assert len(possible_dates) == 4

    # reserve half of the slots
    time = (datetime(2011, 1, 1, 15), datetime(2011, 1, 1, 15, 30))
    token = scheduler.reserve(u'test@example.org', time)
    slots = scheduler.approve_reservations(token)

    assert len(slots) == 2

    # commit the changes (or we'll hit the db, which at this point is dirty,
    # resulting in a DirtyReadOnlySession exception)
    scheduler.commit()

    # check the remaining slots
    remaining = allocation.free_slots()
    assert len(remaining) == 2
    assert remaining == possible_dates[2:]

    reserved_slots = scheduler.reserved_slots_by_reservation(token).all()

    by_start = lambda s: s.start
    assert list(sorted(slots, key=by_start)) \
        == list(sorted(reserved_slots, key=by_start))

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
    scheduler.remove_reservation(token)
    assert len(allocation.free_slots()) == 2


def test_change_email(scheduler):
    # reserve multiple allocations
    dates = (
        (datetime(2014, 8, 7, 11, 0), datetime(2014, 8, 7, 12, 0)),
        (datetime(2014, 8, 8, 11, 0), datetime(2014, 8, 8, 12, 0))
    )

    scheduler.allocate(dates)
    token = scheduler.reserve(u'original@example.org', dates)
    scheduler.commit()

    assert [r.email for r in scheduler.reservations_by_token(token)]\
        == [u'original@example.org'] * 2

    # change the email and ensure that all reservation records are changed
    scheduler.change_email(token, u'newmail@example.org')
    scheduler.commit()

    assert [r.email for r in scheduler.reservations_by_token(token)]\
        == [u'newmail@example.org'] * 2

    # approve the reservation and change again
    scheduler.approve_reservations(token)
    scheduler.change_email(token, u'another@example.org')
    scheduler.commit()

    assert [r.email for r in scheduler.reservations_by_token(token)]\
        == [u'another@example.org'] * 2


def test_change_reservation_assertions(scheduler):
    reservation_changed = Mock()
    events.on_reservation_time_changed.append(reservation_changed)

    dates = (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 17, 0))

    scheduler.allocate(dates, partly_available=False)
    token = scheduler.reserve(u'original@example.org', dates)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(token).one()

    # will fail with an assertion because the reservation was not approved
    with pytest.raises(AssertionError) as assertion:
        scheduler.change_reservation_time(token, reservation.id, *dates)
    assert "must be approved" in str(assertion.value)

    assert scheduler.change_reservation_time_candidates().count() == 0
    assert not reservation_changed.called

    scheduler.approve_reservations(token)
    scheduler.commit()

    # fail with an assertion as the allocation is not partly available
    with pytest.raises(AssertionError) as assertion:
        scheduler.change_reservation_time(
            token, reservation.id, datetime.now(), datetime.now()
        )
    assert "must be partly available" in str(assertion.value)

    assert scheduler.change_reservation_time_candidates().count() == 0
    assert not reservation_changed.called

    # let's try it again with a group allocation (which should also fail)
    dates = (
        (datetime(2014, 8, 10, 11, 0), datetime(2014, 8, 10, 12, 0)),
        (datetime(2014, 8, 11, 11, 0), datetime(2014, 8, 11, 12, 0))
    )

    scheduler.allocate(dates, partly_available=True, grouped=True)
    token = scheduler.reserve(u'original@example.org', dates)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(token).one()
    scheduler.approve_reservations(token)
    scheduler.commit()

    with pytest.raises(MultipleResultsFound):
        scheduler.change_reservation_time(
            token, reservation.id, datetime.now(), datetime.now()
        )

    assert scheduler.change_reservation_time_candidates().count() == 0
    assert not reservation_changed.called

    # fail if the dates are outside the allocation
    dates = (datetime(2014, 3, 7, 8, 0), datetime(2014, 3, 7, 17, 0))

    scheduler.allocate(dates, partly_available=True)
    token = scheduler.reserve(u'original@example.org', dates)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(token).one()
    scheduler.approve_reservations(token)
    scheduler.commit()

    assert scheduler.change_reservation_time_candidates().count() == 1
    assert not reservation_changed.called

    # make sure that the timerange given fits inside the allocation
    with pytest.raises(errors.TimerangeTooLong):
        scheduler.change_reservation_time(
            token, reservation.id,
            datetime(2014, 3, 7, 7, 0), datetime(2014, 3, 7, 17, 0)
        )

    with pytest.raises(errors.TimerangeTooLong):
        scheduler.change_reservation_time(
            token, reservation.id,
            datetime(2014, 3, 7, 8, 0), datetime(2014, 3, 7, 17, 1)
        )


def test_change_reservation(scheduler):
    reservation_changed = Mock()
    events.on_reservation_time_changed.append(reservation_changed)

    dates = (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 10, 0))

    scheduler.allocate(dates, partly_available=True)

    data = {
        'foo': 'bar'
    }
    token = scheduler.reserve(u'original@example.org', (
        datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 9)
    ), data=data)

    scheduler.commit()

    reservation = scheduler.reservations_by_token(token).one()
    original_id = reservation.id

    scheduler.approve_reservations(token)
    scheduler.commit()

    assert scheduler.change_reservation_time_candidates().count() == 1

    # make sure that no changes are made in these cases
    assert not scheduler.change_reservation_time(
        token, reservation.id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 9)
    )

    assert not scheduler.change_reservation_time(
        token, reservation.id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 9) - timedelta(microseconds=1)
    )

    assert not reservation_changed.called

    # make sure the change is propagated
    scheduler.change_reservation_time(
        token, reservation.id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 10)
    )
    scheduler.commit()

    assert reservation_changed.called
    assert reservation_changed.call_args[0][0] == scheduler.context.name
    assert reservation_changed.call_args[1]['old_time'][0].hour == 8
    assert reservation_changed.call_args[1]['old_time'][1].hour == 9
    assert reservation_changed.call_args[1]['new_time'][0].hour == 8
    assert reservation_changed.call_args[1]['new_time'][1].hour == 10

    reservation = scheduler.reservations_by_token(token).one()

    assert reservation.start == calendar.normalize_date(
        datetime(2014, 8, 7, 8, 0), scheduler.timezone
    )
    assert reservation.end == calendar.normalize_date(
        datetime(2014, 8, 7, 10, 0) - timedelta(microseconds=1),
        scheduler.timezone
    )

    # the data must stay the same
    assert reservation.data == data
    assert reservation.email == u'original@example.org'
    assert reservation.id == original_id
    assert reservation.token == token

    scheduler.change_reservation_time(
        token, reservation.id,
        datetime(2014, 8, 7, 9, 0),
        datetime(2014, 8, 7, 10, 0)
    )

    scheduler.approve_reservations(
        scheduler.reserve(u'original@example.org', (
            datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 9)
        ))
    )

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.change_reservation_time(
            token, reservation.id,
            datetime(2014, 8, 7, 8, 0),
            datetime(2014, 8, 7, 10, 0)
        )
