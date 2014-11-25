import pytest

from datetime import datetime, timedelta
from libres.db.models import Reservation, Allocation, ReservedSlot
from libres.modules import calendar, errors, events
from mock import Mock
from sqlalchemy.orm.exc import MultipleResultsFound
from uuid import uuid4 as new_uuid


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

    # be sure to clean up afterwards as this won't be done automatically
    s2.extinguish_managed_records()
    s2.commit()


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


def test_change_reservation_quota(scheduler):
    dates = (
        datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 10, 0)
    )

    scheduler.allocate(dates, partly_available=True, quota=2)

    # have three reservations, one occupying the whole allocation,
    # two others occupying one half each (1 + .5 +.5 = 2 (quota))
    tokens = [
        scheduler.reserve(u'original@example.org', (
            datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 10, 0)
        )),
        scheduler.reserve(u'original@example.org', (
            datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 9, 0)
        )),
        scheduler.reserve(u'original@example.org', (
            datetime(2014, 8, 7, 9, 0), datetime(2014, 8, 7, 10, 0)
        ))
    ]
    scheduler.commit()

    assert scheduler.change_reservation_time_candidates().count() == 0

    for token in tokens:
        scheduler.approve_reservations(token)

    scheduler.commit()

    assert scheduler.change_reservation_time_candidates().count() == 3
    reservation = scheduler.reservations_by_token(tokens[2]).one()

    # with 100% occupancy we can't change one of the small reservations
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.change_reservation_time(
            tokens[2], reservation.id,
            datetime(2014, 8, 7, 8, 0),
            datetime(2014, 8, 7, 10, 0)
        )

    # ensure that the failed removal didn't affect the reservations
    # (a rollback should have occured)
    for token in tokens:
        assert scheduler.reservations_by_token(token).one().token == token

    # removing the big reservation allows us to scale the other two
    scheduler.remove_reservation(tokens[0])

    assert scheduler.change_reservation_time(
        tokens[2], reservation.id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 10, 0)
    )

    reservation = scheduler.reservations_by_token(tokens[1]).one()
    assert scheduler.change_reservation_time(
        tokens[1], reservation.id,
        datetime(2014, 8, 7, 8, 0),
        datetime(2014, 8, 7, 10, 0)
    )


def test_group_reserve(scheduler):
    dates = [
        (datetime(2013, 4, 6, 12, 0), datetime(2013, 4, 6, 16, 0)),
        (datetime(2013, 4, 7, 12, 0), datetime(2013, 4, 7, 16, 0))
    ]

    allocations = scheduler.allocate(
        dates, grouped=True, approve_manually=True, quota=3
    )

    assert len(allocations) == 2

    group = allocations[0].group

    # reserve the same thing three times, which should yield equal results
    def reserve():
        token = scheduler.reserve(u'test@example.com', group=group)
        scheduler.commit()

        reservation = scheduler.reservations_by_token(token).one()

        targets = reservation._target_allocations().all()
        assert len(targets) == 2

        scheduler.approve_reservations(token)
        scheduler.commit()

        targets = reservation._target_allocations().all()
        assert len(targets) == 2

    reserve()
    reserve()
    reserve()

    # the fourth time will fail
    with pytest.raises(errors.AlreadyReservedError):
        reserve()


def test_session_expiration(scheduler):
    session_id = new_uuid()

    start, end = datetime(2013, 5, 1, 13, 0), datetime(2013, 5, 1, 14)
    scheduler.allocate(dates=(start, end), approve_manually=True)
    scheduler.reserve(u'test@example.com', (start, end), session_id=session_id)
    scheduler.commit()

    created = calendar.utcnow()

    # Do NOT use the serial session directly outside of tests!
    res = scheduler.context.serial_session.query(Reservation)
    res = res.filter(Reservation.session_id == session_id)
    res.update({'created': created, 'modified': None})

    scheduler.commit()

    expired = scheduler.queries.find_expired_reservation_sessions(
        expiration_date=created
    )
    assert len(expired) == 0

    expired = scheduler.queries.find_expired_reservation_sessions(
        expiration_date=created + timedelta(microseconds=1)
    )
    assert len(expired) == 1

    # Do NOT use the serial session directly outside of tests!
    res = scheduler.context.serial_session.query(Reservation)
    res = res.filter(Reservation.session_id == session_id)
    res.update({
        'created': created,
        'modified': created + timedelta(microseconds=1)
    })

    scheduler.commit()

    expired = scheduler.queries.find_expired_reservation_sessions(
        expiration_date=created + timedelta(microseconds=1)
    )
    assert len(expired) == 0

    expired = scheduler.queries.find_expired_reservation_sessions(
        expiration_date=created + timedelta(microseconds=2)
    )
    assert len(expired) == 1


def test_session_removal_is_complete(scheduler):
    start, end = datetime(2013, 9, 27, 9, 0), datetime(2013, 9, 27, 10)
    scheduler.allocate(dates=(start, end))
    session_id = new_uuid()

    token = scheduler.reserve(
        u'test@example.org', (start, end), session_id=session_id
    )

    scheduler.commit()

    assert scheduler.session.query(Reservation).count() == 1
    assert scheduler.session.query(Allocation).count() == 1
    assert scheduler.session.query(ReservedSlot).count() == 0

    scheduler.approve_reservations(token)
    scheduler.commit()

    assert scheduler.session.query(Reservation).count() == 1
    assert scheduler.session.query(Allocation).count() == 1
    assert scheduler.session.query(ReservedSlot).count() == 1

    scheduler.queries.remove_expired_reservation_sessions(
        expiration_date=calendar.utcnow() + timedelta(seconds=15 * 60)
    )
    scheduler.commit()

    assert scheduler.session.query(Reservation).count() == 0
    assert scheduler.session.query(Allocation).count() == 1
    assert scheduler.session.query(ReservedSlot).count() == 0
