import pytest
import sedate

from copy import copy
from datetime import date, datetime, timedelta, time
from libres.db.models import Reservation, Allocation
from libres.modules import errors, events
from libres.modules import utils
from mock import Mock
from sqlalchemy.exc import StatementError
from sqlalchemy.orm.exc import MultipleResultsFound
from uuid import uuid4 as new_uuid


def test_rollback(scheduler):

    # write something in the transaction
    scheduler.allocate(
        (datetime(2014, 4, 4, 14, 0), datetime(2014, 4, 4, 15, 0))
    )

    # rollback the transaction
    scheduler.rollback()

    # nothing should have happened
    assert scheduler.managed_allocations().count() == 0


def test_manual_approval_required(scheduler):
    dates = [
        (datetime(2014, 4, 4, 14, 0), datetime(2014, 4, 4, 15, 0)),
        (datetime(2015, 4, 4, 14, 0), datetime(2015, 4, 4, 15, 0))
    ]

    aut = [a.id for a in scheduler.allocate(dates[:1], approve_manually=False)]
    man = [a.id for a in scheduler.allocate(dates[1:], approve_manually=True)]
    scheduler.commit()

    assert not scheduler.manual_approval_required(aut)
    assert scheduler.manual_approval_required(man)
    assert scheduler.manual_approval_required(aut + man)


def test_allocations_to_whole_day(scheduler):

    dates = (datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 11))
    allocations = scheduler.allocate(dates)
    scheduler.commit()

    assert not allocations[0].whole_day

    scheduler.move_allocation(
        allocations[0].id,
        new_start=dates[0],
        new_end=dates[1],
        whole_day=True
    )
    scheduler.commit()

    assert allocations[0].whole_day


def test_move_allocation_over_existing(scheduler):
    dates = [
        (datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 11)),
        (datetime(2015, 2, 9, 11), datetime(2015, 2, 9, 12)),
    ]

    allocations = scheduler.allocate(dates)
    scheduler.commit()

    with pytest.raises(errors.OverlappingAllocationError):
        scheduler.move_allocation(
            allocations[0].id,
            new_start=datetime(2015, 2, 9, 10),
            new_end=datetime(2015, 2, 9, 12)
        )


def test_move_allocation_with_existing_reservation(scheduler):
    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 11))]

    allocations = scheduler.allocate(dates)
    token = scheduler.reserve('test@example.org', dates)
    scheduler.commit()

    # This allocation is not partly available, so any change is prohibited
    # if a pending reservation exists.
    with pytest.raises(errors.AffectedPendingReservationError):
        scheduler.move_allocation(
            allocations[0].id,
            new_start=datetime(2015, 2, 9, 10),
            new_end=datetime(2015, 2, 9, 12)
        )

    scheduler.approve_reservations(token)
    scheduler.commit()

    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            allocations[0].id,
            new_start=datetime(2015, 2, 9, 10),
            new_end=datetime(2015, 2, 9, 12)
        )


def test_move_partly_available_allocation_with_existing_reservation(scheduler):
    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    allocations = scheduler.allocate(dates, partly_available=True)
    scheduler.reserve('test@example.org', dates)
    scheduler.commit()

    # partly available allocations cannot be shrunk smaller if a
    # reservation covers that spot...
    with pytest.raises(errors.AffectedPendingReservationError):
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


def test_change_allocation_data(scheduler):
    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    allocation = scheduler.allocate(dates, data={'foo': 'bar'})[0]
    scheduler.commit()
    assert allocation.data == {'foo': 'bar'}

    # yes, this a very awkward way to change an allocation's data...
    scheduler.move_allocation(
        allocation.id, new_start=dates[0][0], new_end=dates[0][1], data={
            'bar': 'foo'
        },
    )
    scheduler.commit()
    assert allocation.data == {'bar': 'foo'}


def test_change_reservation_data(scheduler):

    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    allocation = scheduler.allocate(dates)[0]
    token = scheduler.reserve(
        email='test@example.org', dates=dates, data={'foo': 'bar'})
    scheduler.commit()

    reservation = scheduler.reservations_by_allocation(allocation.id).one()
    assert reservation.data == {'foo': 'bar'}

    scheduler.change_reservation_data(token, data={'bar': 'foo'})
    scheduler.commit()

    assert reservation.data == {'bar': 'foo'}


def test_reserve_quota(scheduler):
    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    scheduler.allocate(dates, quota=2, quota_limit=1)
    scheduler.commit()

    with pytest.raises(errors.InvalidQuota):
        scheduler.reserve('test@example.org', dates=dates, quota=0)

    with pytest.raises(errors.QuotaOverLimit):
        scheduler.reserve('test@example.org', dates=dates, quota=2)

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.reserve('test@example.org', dates=dates, quota=3)


def test_reserve_impossible_quota(scheduler):

    dates = [(datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12))]

    scheduler.allocate(dates, quota=2, approve_manually=True)
    scheduler.commit()

    with pytest.raises(errors.QuotaImpossible):
        scheduler.reserve('test@example.org', dates=dates, quota=3)


def test_remove_allocation_with_pending_reservation(scheduler):
    dates = [
        (datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12)),
        (datetime(2015, 2, 10, 10), datetime(2015, 2, 10, 12)),
    ]

    id = scheduler.allocate(dates, grouped=True, approve_manually=True)[0].id
    scheduler.reserve(email='test@example.org', dates=dates)
    scheduler.commit()

    with pytest.raises(errors.AffectedPendingReservationError):
        scheduler.remove_allocation(id)


def test_remove_grouped_allocation(scheduler):
    dates = [
        (datetime(2015, 2, 9, 10), datetime(2015, 2, 9, 12)),
        (datetime(2015, 2, 10, 10), datetime(2015, 2, 10, 12)),
    ]

    group = scheduler.allocate(dates, grouped=True)[0].group
    scheduler.commit()

    assert scheduler.managed_allocations().count() == 2

    scheduler.remove_allocation(groups=[group])
    scheduler.commit()

    assert scheduler.managed_allocations().count() == 0


def test_remove_allocation_with_quota_regression(scheduler):
    dates = [(datetime(2015, 2, 13, 10), datetime(2015, 2, 13, 12))]
    allocation = scheduler.allocate(dates, quota=10)[0]

    scheduler.commit()
    scheduler.remove_allocation(allocation.id)


def test_invalid_new_allocation(scheduler):
    dates = [(datetime(2015, 2, 14, 10), datetime(2015, 2, 13, 12))]

    with pytest.raises(errors.InvalidAllocationError):
        scheduler.allocate(dates, quota=10)[0]


def test_invalid_move_allocation(scheduler):
    dates = [(datetime(2015, 2, 13, 10), datetime(2015, 2, 13, 12))]
    allocation = scheduler.allocate(dates, quota=10)[0]

    with pytest.raises(errors.InvalidAllocationError):
        scheduler.move_allocation(
            allocation.id,
            new_start=allocation.end,
            new_end=allocation.start
        )


def test_reserve_invalid_email(scheduler):

    with pytest.raises(errors.InvalidEmailAddress):
        scheduler.reserve(group='foo', email='invalid-email')


def test_reservation_too_short(scheduler):

    with pytest.raises(errors.ReservationTooShort):
        scheduler.reserve(email='test@example.org', dates=[
            (datetime(2015, 2, 9, 10, 0), datetime(2015, 2, 9, 10, 1)),
        ])


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
        (start, end), partly_available=True, raster=15
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

    def by_start(s):
        return s.start

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
    scheduler.session.refresh(allocation)
    assert len(allocation.free_slots()) == 2


def test_reserve_single_token_per_session(scheduler):

    session_id = new_uuid()

    a1, a2 = scheduler.allocate(
        dates=(
            datetime(2011, 1, 1, 15), datetime(2011, 1, 1, 16),
            datetime(2011, 1, 2, 15), datetime(2011, 1, 2, 16)
        ),
        quota=1
    )

    token1 = scheduler.reserve(
        email=u'test@example.org',
        dates=(a1.start, a1.end),
        session_id=session_id,
        single_token_per_session=True
    )

    token2 = scheduler.reserve(
        email=u'test@example.org',
        dates=(a2.start, a2.end),
        session_id=session_id,
        single_token_per_session=True
    )

    assert token1 == token2

    scheduler.remove_reservation(token1)

    token3 = scheduler.reserve(
        email=u'test@example.org',
        dates=(a1.start, a1.end),
        session_id=session_id,
        single_token_per_session=True
    )

    token4 = scheduler.reserve(
        email=u'test@example.org',
        dates=(a2.start, a2.end),
        session_id=session_id,
        single_token_per_session=True
    )

    assert token1 != token3
    assert token3 == token4


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
    scheduler.approve_reservations(token)
    scheduler.commit()

    dates = (
        (datetime(2014, 8, 10, 11, 0), datetime(2014, 8, 10, 12, 0)),
        (datetime(2014, 8, 11, 11, 0), datetime(2014, 8, 11, 12, 0))
    )

    scheduler.allocate(dates, grouped=True)
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


def test_change_unapproved_reservation_quota(scheduler):
    dates = (datetime(2014, 8, 7, 8, 0), datetime(2014, 8, 7, 10, 0))
    scheduler.allocate(dates, quota=2)

    token = scheduler.reserve(
        u'original@example.org', dates, session_id=new_uuid().hex
    )

    scheduler.commit()

    reservation = scheduler.reservations_by_token(token).one()
    assert not scheduler.change_reservation(
        token=token,
        id=reservation.id,
        new_start=reservation.start,
        new_end=reservation.end,
        quota=1
    )

    assert scheduler.change_reservation(
        token=token,
        id=reservation.id,
        new_start=reservation.start,
        new_end=reservation.end,
        quota=2
    )

    new = scheduler.reservations_by_token(reservation.token).first()
    assert new.quota == 2
    assert new.session_id and new.session_id == reservation.session_id


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
    assert reservation_changed.call_args[0][0].name == scheduler.context.name
    assert reservation_changed.call_args[1]['old_time'][0].hour == 8
    assert reservation_changed.call_args[1]['old_time'][1].hour == 9
    assert reservation_changed.call_args[1]['new_time'][0].hour == 8
    assert reservation_changed.call_args[1]['new_time'][1].hour == 10

    reservation = scheduler.reservations_by_token(token).one()

    assert reservation.start == sedate.standardize_date(
        datetime(2014, 8, 7, 8, 0), scheduler.timezone
    )
    assert reservation.end == sedate.standardize_date(
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

    created = sedate.utcnow()

    res = scheduler.session.query(Reservation)
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

    res = scheduler.session.query(Reservation)
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


def test_session_removal(scheduler):
    start, end = datetime(2013, 9, 27, 9, 0), datetime(2013, 9, 27, 10)
    scheduler.allocate(dates=(start, end))
    session_id = new_uuid()

    scheduler.reserve(u'test@example.org', (start, end), session_id=session_id)
    scheduler.commit()

    assert scheduler.session.query(Reservation).count() == 1
    assert scheduler.session.query(Allocation).count() == 1

    scheduler.queries.remove_expired_reservation_sessions(
        expiration_date=sedate.utcnow() + timedelta(seconds=15 * 60)
    )
    scheduler.commit()

    assert scheduler.session.query(Reservation).count() == 0
    assert scheduler.session.query(Allocation).count() == 1


def test_invalid_reservation(scheduler):
    # try to reserve aspot that doesn't exist
    astart = datetime(2012, 1, 1, 15, 0)
    aend = datetime(2012, 1, 1, 16, 0)
    adates = (astart, aend)

    rstart = datetime(2012, 2, 1, 15, 0)
    rend = datetime(2012, 2, 1, 16, 0)
    rdates = (rstart, rend)

    scheduler.allocate(dates=adates, approve_manually=True)

    with pytest.raises(errors.InvalidReservationError):
        scheduler.reserve(u'test@example.org', rdates)


def test_waitinglist(scheduler):
    start = datetime(2012, 2, 29, 15, 0)
    end = datetime(2012, 2, 29, 19, 0)
    dates = (start, end)

    # let's create an allocation with a waitinglist
    allocation = scheduler.allocate(dates, approve_manually=True)[0]
    assert allocation.waitinglist_length == 0

    # reservation should work
    approval_token = scheduler.reserve(u'test@example.org', dates)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(approval_token).one()

    assert not reservation.autoapprovable
    assert allocation.is_available(start, end)
    assert allocation.waitinglist_length == 1

    # as well as it's approval
    scheduler.approve_reservations(approval_token)
    scheduler.commit()

    assert not allocation.is_available(start, end)
    assert allocation.waitinglist_length == 0

    # at this point we can only reserve, not approve
    waiting_token = scheduler.reserve(u'test@example.org', dates)
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.approve_reservations(waiting_token)

    assert allocation.waitinglist_length == 1

    # try to illegally move the allocation now
    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(
            allocation.id, start + timedelta(days=1), end + timedelta(days=1)
        )

    # we may now get rid of the existing approved reservation
    scheduler.remove_reservation(approval_token)
    scheduler.commit()

    assert allocation.waitinglist_length == 1

    # which should allow us to approve the reservation in the waiting list
    scheduler.approve_reservations(waiting_token)
    scheduler.commit()

    assert allocation.waitinglist_length == 0


def test_no_bleed(scheduler):
    """ Ensures that two allocations close to each other are not mistaken
    when using scheduler.reserve. If they do then they bleed over, hence
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
    scheduler.reserve(u'test@example.org', d2)
    scheduler.reserve(u'test@example.org', d1)


def test_waitinglist_group(scheduler):
    from dateutil.rrule import rrule, DAILY, MO

    days = list(rrule(
        DAILY, count=5, byweekday=(MO,), dtstart=datetime(2012, 1, 1)
    ))
    dates = []
    for d in days:
        dates.append(
            (
                datetime(d.year, d.month, d.day, 15, 0),
                datetime(d.year, d.month, d.day, 16, 0)
            )
        )

    allocations = scheduler.allocate(
        dates, grouped=True, approve_manually=True
    )
    assert len(allocations) == 5

    group = allocations[0].group

    # reserving groups is no different than single allocations
    maintoken = scheduler.reserve(u'test@example.org', group=group)
    scheduler.commit()

    reservation = scheduler.reservations_by_token(maintoken).one()

    assert not reservation.autoapprovable

    for allocation in allocations:
        assert allocation.waitinglist_length == 1

    scheduler.approve_reservations(maintoken)
    scheduler.commit()

    token = scheduler.reserve(u'test@example.org', group=group)
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.approve_reservations(token)

    token = scheduler.reserve(u'test@example.org', group=group)
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.approve_reservations(token)

    scheduler.remove_reservation(maintoken)
    scheduler.approve_reservations(token)


def test_group_move(scheduler):
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

    token = scheduler.reserve(u'test@example.com', group=allocations[0].group)
    scheduler.approve_reservations(token)
    scheduler.commit()

    group_allocations = scheduler.allocations_by_group(
        allocations[0].group).all()
    assert len(group_allocations) == 2

    all = utils.flatten([a.siblings() for a in group_allocations])
    assert scheduler.queries.availability_by_allocations(all) == 50.0

    scheduler.move_allocation(
        allocations[0].id, newstart, newend, new_quota=1
    )
    scheduler.commit()

    group_allocations = scheduler.allocations_by_group(
        allocations[0].group).all()
    all = list(utils.flatten([a.siblings() for a in group_allocations]))
    assert scheduler.queries.availability_by_allocations(all) == 0.0

    scheduler.move_allocation(allocations[0].id, newstart, newend, new_quota=2)
    scheduler.commit()

    token = scheduler.reserve(u'test@example.com', group=allocations[0].group)
    scheduler.approve_reservations(token)
    scheduler.commit()

    group_allocations = scheduler.allocations_by_group(
        allocations[0].group).all()
    all = list(utils.flatten([a.siblings() for a in group_allocations]))
    assert scheduler.queries.availability_by_allocations(all) == 0.0

    for a in all:
        assert not a.is_available()

    assert len(all) == 4

    with pytest.raises(errors.AffectedReservationError):
        scheduler.move_allocation(allocations[0].id, newstart, newend, None, 1)


def test_no_waitinglist(scheduler):

    start = datetime(2012, 4, 6, 22, 0)
    end = datetime(2012, 4, 6, 23, 0)
    dates = (start, end)

    allocation = scheduler.allocate(dates, approve_manually=False)[0]
    scheduler.commit()

    assert allocation.waitinglist_length == 0

    # the first reservation kinda gets us in a waiting list, though
    # this time there can be only one spot in the list as long as there's
    # no reservation

    token = scheduler.reserve(u'test@example.org', dates)
    scheduler.commit()

    assert scheduler.reservations_by_token(token).one().autoapprovable
    scheduler.approve_reservations(token)
    scheduler.commit()

    # it is now that we should have a problem reserving
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.reserve(u'test@example.org', dates)
    assert allocation.waitinglist_length == 0

    # until we delete the existing reservation
    scheduler.remove_reservation(token)
    scheduler.reserve(u'test@example.org', dates)


def test_quota_waitinglist(scheduler):
    start = datetime(2012, 3, 4, 2, 0)
    end = datetime(2012, 3, 4, 3, 0)
    dates = (start, end)

    # in this example the waiting list will kick in only after
    # the quota has been filled

    allocation = scheduler.allocate(dates, quota=2, approve_manually=True)[0]
    assert allocation.waitinglist_length == 0

    t1 = scheduler.reserve(u'test@example.org', dates)
    t2 = scheduler.reserve(u'test@example.org', dates)
    scheduler.commit()

    assert allocation.waitinglist_length == 2

    scheduler.approve_reservations(t1)
    scheduler.approve_reservations(t2)
    scheduler.commit()

    assert allocation.waitinglist_length == 0

    t3 = scheduler.reserve(u'test@example.org', dates)
    t4 = scheduler.reserve(u'test@example.org', dates)
    scheduler.commit()

    assert allocation.waitinglist_length == 2

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.approve_reservations(t3)

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.approve_reservations(t4)


def test_userlimits(scheduler):
    # ensure that no user can make a reservation for more than 24 hours at
    # the time. the user acutally can't do that anyway, since we do not
    # offer start / end dates, but a day and two times. But if this changes
    # in the future it should throw en error first, because it would mean
    # that we have to look at how to stop the user from reserving one year
    # with a single form.

    start = datetime(2011, 1, 1, 15, 0)
    end = start + timedelta(days=1)

    with pytest.raises(errors.ReservationTooLong):
        scheduler.reserve(u'test@example.org', (start, end))


def test_allocation_overlap(scheduler):

    sc1 = scheduler
    sc2 = scheduler.clone()
    sc2.name = 'clone'

    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)

    sc1.allocate((start, end), raster=15)
    sc1.commit()

    sc2.allocate((start, end), raster=15)
    sc2.commit()

    with pytest.raises(errors.OverlappingAllocationError):
        sc1.allocate((start, end), raster=15)

    # there's another way this could happen, which is illegal usage
    # of scheduler.allocate - we stop this befor it hits the database
    sc3 = scheduler.clone()
    sc3.name = 'another_clone'

    dates = [
        (datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0)),
        (datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0))
    ]

    with pytest.raises(errors.InvalidAllocationError):
        sc3.allocate(dates)

    dates = [
        (datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 1)),
        (datetime(2013, 1, 1, 13, 0), datetime(2013, 1, 1, 14, 0))
    ]

    with pytest.raises(errors.InvalidAllocationError):
        sc3.allocate(dates)

    dates = [
        (datetime(2013, 1, 1, 12, 0), datetime(2013, 1, 1, 13, 0)),
        (datetime(2013, 1, 1, 13, 0), datetime(2013, 1, 1, 14, 0))
    ]

    allocations = sc3.allocate(dates)
    sc3.commit()

    assert allocations[0]._end < allocations[1]._start

    # only sc1 is cleaned up automatically
    sc2.extinguish_managed_records()
    sc2.commit()

    sc3.extinguish_managed_records()
    sc3.commit()


def test_allocation_partition(scheduler):
    allocations = scheduler.allocate(
        (
            datetime(2011, 1, 1, 8, 0),
            datetime(2011, 1, 1, 10, 0)
        ),
        partly_available=True
    )

    allocation = allocations[0]
    partitions = allocation.availability_partitions()
    assert len(partitions) == 1
    assert partitions[0][0] == 100.0
    assert partitions[0][1] == False

    start, end = datetime(2011, 1, 1, 8, 30), datetime(2011, 1, 1, 9, 00)

    token = scheduler.reserve(u'test@example.org', (start, end))
    scheduler.approve_reservations(token)
    scheduler.commit()

    partitions = allocation.availability_partitions()
    assert len(partitions) == 3
    assert partitions[0][0] == 25.00
    assert partitions[0][1] == False
    assert partitions[1][0] == 25.00
    assert partitions[1][1] == True
    assert partitions[2][0] == 50.00
    assert partitions[2][1] == False


def test_partly(scheduler):
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

    token = scheduler.reserve(
        u'info@example.org',
        (datetime(2011, 1, 1, 16, 0), datetime(2011, 1, 1, 18, 0))
    )
    scheduler.approve_reservations(token)

    with pytest.raises(errors.AlreadyReservedError):
        scheduler.reserve(u'info@example.org', (
            datetime(2011, 1, 1, 8, 0), datetime(2011, 1, 1, 9, 0)
        ))


def test_allocation_by_ids(scheduler):
    dates = [
        (datetime(2015, 1, 1, 15, 0), datetime(2015, 1, 1, 16, 0)),
        (datetime(2015, 1, 2, 15, 0), datetime(2015, 1, 2, 16, 0)),
    ]

    ids = [a.id for a in scheduler.allocate(dates)]
    scheduler.commit()

    assert scheduler.allocations_by_ids(ids).count() == 2


def test_allocation_dates_by_ids(scheduler):
    dates = [
        (datetime(2015, 1, 1, 15, 0), datetime(2015, 1, 1, 16, 0)),
        (datetime(2015, 1, 2, 15, 0), datetime(2015, 1, 2, 16, 0)),
    ]

    ids = [a.id for a in scheduler.allocate(dates, partly_available=True)]
    scheduler.commit()

    d = list(scheduler.allocation_dates_by_ids(ids))

    def standardize(dt):
        return sedate.standardize_date(dt, 'Europe/Zurich')

    def as_utc(dt):
        return sedate.to_timezone(dt, 'UTC')

    assert as_utc(d[0][0]) == standardize(dates[0][0])
    assert as_utc(d[0][1]) == standardize(dates[0][1]) - timedelta(
        microseconds=1)
    assert as_utc(d[1][0]) == standardize(dates[1][0])
    assert as_utc(d[1][1]) == standardize(dates[1][1]) - timedelta(
        microseconds=1)

    d = list(scheduler.allocation_dates_by_ids(
        ids, start_time=time(15, 0), end_time=time(15, 30)))

    assert d[0][0] == standardize(dates[0][0])
    assert d[0][1] == standardize(dates[0][1]) - timedelta(
        microseconds=1, seconds=30 * 60)
    assert d[1][0] == standardize(dates[1][0])
    assert d[1][1] == standardize(dates[1][1]) - timedelta(
        microseconds=1, seconds=30 * 60)


def test_quotas(scheduler):
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)

    # setup an allocation with ten spots
    allocations = scheduler.allocate(
        (start, end), raster=15, quota=10, approve_manually=False
    )
    allocation = allocations[0]
    scheduler.commit()

    # which should give us ten allocations (-1 as the master is not
    # counted)
    assert len(scheduler.allocation_mirrors_by_master(allocation)) == 9

    # the same reservation can now be made ten times
    for i in range(0, 10):
        scheduler.approve_reservations(
            scheduler.reserve(u'test@example.org', (start, end))
        )
    scheduler.commit()

    # the 11th time it'll fail
    with pytest.raises(errors.AlreadyReservedError):
        scheduler.reserve(u'test@example.org', [(start, end)])

    other = scheduler.clone()
    other.name = 'other'

    # setup an allocation with five spots
    allocations = other.allocate(
        [(start, end)], raster=15, quota=5, partly_available=True,
        approve_manually=False
    )
    allocation = allocations[0]

    assert len(other.allocation_mirrors_by_master(allocation)) == 4

    # we can do ten reservations if every reservation only occupies half
    # of the allocation
    for i in range(0, 5):
        other.approve_reservations(
            other.reserve(
                u'test@example.org',
                (datetime(2011, 1, 1, 15, 0), datetime(2011, 1, 1, 15, 30))
            )
        )
        other.approve_reservations(
            other.reserve(
                u'test@example.org',
                (datetime(2011, 1, 1, 15, 30), datetime(2011, 1, 1, 16, 0))
            )
        )

    scheduler.commit()

    with pytest.raises(errors.AlreadyReservedError):
        other.reserve(u'test@example.org', (
            (datetime(2011, 1, 1, 15, 30), datetime(2011, 1, 1, 16, 0))
        ))

    # test some queries
    allocations = scheduler.allocations_in_range(start, end)
    assert allocations.count() == 1

    allocations = other.allocations_in_range(start, end)
    assert allocations.count() == 1

    allocation = scheduler.allocation_by_date(start, end)
    scheduler.allocation_by_id(allocation.id)
    assert len(scheduler.allocation_mirrors_by_master(allocation)) == 9

    allocation = other.allocation_by_date(start, end)
    other.allocation_by_id(allocation.id)
    assert len(other.allocation_mirrors_by_master(allocation)) == 4

    other.extinguish_managed_records()
    other.commit()


def test_fragmentation(scheduler):
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)
    daterange = (start, end)

    allocation = scheduler.allocate(daterange, quota=3)[0]
    reservation = scheduler.reserve(u'test@example.org', daterange)
    slots = scheduler.approve_reservations(reservation)

    assert all(True for s in slots if s.resource == scheduler.resource)

    slots = scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    assert not any(False for s in slots if s.resource == scheduler.resource)

    scheduler.remove_reservation(reservation)

    slots = scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    assert all(True for s in slots if s.resource == scheduler.resource)

    with pytest.raises(errors.AffectedReservationError):
        scheduler.remove_allocation(allocation.id)


def test_imaginary_mirrors(scheduler):
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)
    daterange = (start, end)

    allocation = scheduler.allocate(daterange, quota=3)[0]
    assert allocation.is_master

    mirrors = scheduler.allocation_mirrors_by_master(allocation)
    imaginary = len([m for m in mirrors if m.is_transient])
    assert imaginary == 2
    assert len(allocation.siblings()) == 3

    masters = len([m for m in mirrors if m.is_master])
    assert masters == 0
    assert len([s for s in allocation.siblings(imaginary=False)]) == 1

    scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    mirrors = scheduler.allocation_mirrors_by_master(allocation)
    imaginary = len([m for m in mirrors if m.is_transient])
    assert imaginary == 2

    scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    mirrors = scheduler.allocation_mirrors_by_master(allocation)
    imaginary = len([m for m in mirrors if m.is_transient])
    assert imaginary == 1

    scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    mirrors = scheduler.allocation_mirrors_by_master(allocation)
    imaginary = len([m for m in mirrors if m.is_transient])
    assert imaginary == 0
    assert len(mirrors) + 1 == len(allocation.siblings())


def test_allocations_by_reservation(scheduler):
    start = datetime(2013, 12, 3, 13, 0)
    end = datetime(2013, 12, 3, 15, 0)
    daterange = (start, end)

    allocations = scheduler.allocate(daterange, approve_manually=True)
    token = scheduler.reserve(u'test@example.org', daterange)
    scheduler.commit()

    # pending reservations return empty
    assert scheduler.allocations_by_reservation(token).all() == []

    # on the reservation itself, the target can be found however
    reservation = scheduler.reservations_by_token(token).one()
    assert reservation._target_allocations().all() == allocations

    # note how this changes once the reservation is approved
    scheduler.approve_reservations(token)
    scheduler.commit()

    assert scheduler.allocations_by_reservation(token).all() == allocations

    # all the while it stays the same here
    assert reservation._target_allocations().all() == allocations


def test_allocations_by_multiple_reservations(scheduler):
    ranges = (
        (datetime(2013, 12, 3, 13, 0), datetime(2013, 12, 3, 15, 0)),
        (datetime(2014, 12, 3, 13, 0), datetime(2014, 12, 3, 15, 0))
    )

    allocations = []
    for start, end in ranges:
        allocations.extend(
            scheduler.allocate((start, end), approve_manually=True)
        )

    token = scheduler.reserve(u'test@example.org', ranges)
    scheduler.approve_reservations(token)
    scheduler.commit()

    # we now have multiple reservations pointing to multiple tokens
    # bound together in one reservation token
    assert len(scheduler.allocations_by_reservation(token).all()) == 2

    # which we can limit by reservation id
    reservations = scheduler.managed_reservations().all()

    query = scheduler.allocations_by_reservation(token, reservations[0].id)
    assert query.count() == 1

    query = scheduler.allocations_by_reservation(token, reservations[1].id)
    assert query.count() == 1


def test_quota_changes_simple(scheduler):
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)
    daterange = (start, end)
    master = scheduler.allocate(daterange, quota=5)[0]
    assert master.quota_left == 5

    reservations = []
    for i in range(0, 5):
        reservations.append(scheduler.reserve(u'test@example.org', daterange))

    for r in reservations:
        scheduler.approve_reservations(r)

    scheduler.commit()

    mirrors = scheduler.allocation_mirrors_by_master(master)

    assert not master.is_available()
    assert len([m for m in mirrors if not m.is_available()]) == 4
    assert master.quota_left == 0

    scheduler.remove_reservation(reservations[0])
    scheduler.commit()

    assert master.is_available()
    reservations = reservations[1:]

    # by removing the reservation on the master and changing the quota
    # a reordering is triggered which will ensure that the master and the
    # mirrors are reserved without gaps (master, mirror 0, mirror 1 usw..)
    # so we should see an unavailable master after changing the quota
    scheduler.change_quota(master, 4)
    scheduler.commit()

    assert not master.is_available()
    assert master.quota == 4

    mirrors = scheduler.allocation_mirrors_by_master(master)
    assert len([m for m in mirrors if not m.is_available()]) == 3

    for reservation in reservations:
        scheduler.remove_reservation(reservation)
        scheduler.commit()

    assert master.is_available()
    mirrors = scheduler.allocation_mirrors_by_master(master)
    assert len([m for m in mirrors if not m.is_available()]) == 0

    # this is a good time to check if the siblings function from the
    # allocation acts the same on each mirror and master
    siblings = master.siblings()
    for s in siblings:
        assert s.siblings() == siblings


def test_quota_changes_advanced(scheduler):
    # let's do another round, adding 7 reservations and removing the three
    # in the middle, which should result in a reordering:
    # -> 1, 2, 3, 4, 5, 6, 7
    # -> 1, 2, -, -, 5, -, 7
    # => 1, 2, 3, 4, -, - ,-

    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)
    daterange = (start, end)

    master = scheduler.allocate(daterange, quota=7)[0]

    scheduler.change_quota(master, 7)
    scheduler.reserve(u'test@example.org', daterange)
    r2 = scheduler.reserve(u'test@example.org', daterange)
    r3 = scheduler.reserve(u'test@example.org', daterange)
    r4 = scheduler.reserve(u'test@example.org', daterange)
    r5 = scheduler.reserve(u'test@example.org', daterange)
    r6 = scheduler.reserve(u'test@example.org', daterange)
    r7 = scheduler.reserve(u'test@example.org', daterange)

    for r in [r2, r3, r4, r5, r6, r7]:
        scheduler.approve_reservations(r)

    scheduler.commit()

    master.quota_left == 0

    a2 = scheduler.allocations_by_reservation(r2).one().id
    a3 = scheduler.allocations_by_reservation(r3).one().id
    a4 = scheduler.allocations_by_reservation(r4).one().id
    a5 = scheduler.allocations_by_reservation(r5).one().id
    a7 = scheduler.allocations_by_reservation(r7).one().id

    scheduler.remove_reservation(r3)
    scheduler.remove_reservation(r4)
    scheduler.remove_reservation(r6)
    scheduler.commit()

    master.quota_left == 3

    scheduler.change_quota(master, 4)
    scheduler.commit()

    master.quota_left == 0

    a2_ = scheduler.allocations_by_reservation(r2).one().id
    a5_ = scheduler.allocations_by_reservation(r5).one().id
    a7_ = scheduler.allocations_by_reservation(r7).one().id

    assert a2_ == a2

    assert a5_ == a3
    assert a5_ != a5

    assert a7_ == a4
    assert a7_ != a7


def test_availability(scheduler):
    start = datetime(2011, 1, 1, 15, 0)
    end = datetime(2011, 1, 1, 16, 0)

    a = scheduler.allocate(
        (start, end), raster=15, partly_available=True)[0]

    scheduler.approve_reservations(
        scheduler.reserve(
            u'test@example.org',
            (datetime(2011, 1, 1, 15, 0), datetime(2011, 1, 1, 15, 15))
        )
    )
    scheduler.commit()

    assert a.availability == 75.0
    assert a.availability == scheduler.availability()

    scheduler.approve_reservations(
        scheduler.reserve(
            u'test@example.org',
            (datetime(2011, 1, 1, 15, 45), datetime(2011, 1, 1, 16, 0))
        )
    )
    scheduler.commit()

    assert a.availability == 50.0
    assert a.availability == scheduler.availability()

    scheduler.approve_reservations(
        scheduler.reserve(
            u'test@example.org',
            (datetime(2011, 1, 1, 15, 15), datetime(2011, 1, 1, 15, 30))
        )
    )
    scheduler.commit()

    assert a.availability == 25.0
    assert a.availability == scheduler.availability()

    scheduler.approve_reservations(
        scheduler.reserve(
            u'test@example.org',
            (datetime(2011, 1, 1, 15, 30), datetime(2011, 1, 1, 15, 45))
        )
    )
    scheduler.commit()

    assert a.availability == 0.0
    assert a.availability == scheduler.availability()

    sc2 = scheduler.clone()
    sc2.name = 'clone'

    a = sc2.allocate((start, end), quota=4)[0]
    assert a.availability == 100.0  # master only!

    sc2.approve_reservations(sc2.reserve(u'test@example.org', (start, end)))
    sc2.commit()

    assert sc2.availability() == 75.0
    assert a.availability == 0.0  # master only!

    sc2.approve_reservations(
        sc2.reserve(u'test@example.org', (start, end))
    )
    sc2.commit()
    assert sc2.availability() == 50.0

    sc2.approve_reservations(
        sc2.reserve(u'test@example.org', (start, end))
    )
    sc2.commit()
    assert sc2.availability() == 25.0

    sc2.approve_reservations(
        sc2.reserve(u'test@example.org', (start, end))
    )
    sc2.commit()
    assert sc2.availability() == 0.0

    sc2.extinguish_managed_records()
    sc2.commit()


def test_events(scheduler):

    # hookup test event subscribers
    allocations_added = Mock()
    reservations_made = Mock()
    reservations_approved = Mock()
    reservations_denied = Mock()
    reservations_removed = Mock()

    events.on_allocations_added.append(allocations_added)
    events.on_reservations_made.append(reservations_made)
    events.on_reservations_approved.append(reservations_approved)
    events.on_reservations_denied.append(reservations_denied)
    events.on_reservations_removed.append(reservations_removed)

    assert not allocations_added.called
    assert not reservations_made.called
    assert not reservations_approved.called
    assert not reservations_denied.called
    assert not reservations_removed.called

    # prepare reservation
    start = datetime(2012, 2, 29, 15, 0)
    end = datetime(2012, 2, 29, 19, 0)
    dates = (start, end)

    # create allocations
    start = datetime(2012, 1, 1, 15, 0)
    end = datetime(2012, 1, 1, 19, 0)
    dates = (start, end)

    scheduler.allocate(dates, approve_manually=True)
    assert allocations_added.called
    assert allocations_added.call_args[0][0].name == scheduler.context.name
    assert len(allocations_added.call_args[0][1]) == 1

    # create reservations

    token = scheduler.reserve(u'test@example.org', dates)
    assert reservations_made.called
    assert reservations_made.call_args[0][0].name == scheduler.context.name
    assert reservations_made.call_args[0][0].name == scheduler.context.name
    assert reservations_made.call_args[0][1][0].token == token

    reservations_made.reset_mock()

    # approve reservations
    scheduler.approve_reservations(token)

    assert reservations_approved.called
    assert not reservations_denied.called
    assert not reservations_made.called
    assert reservations_approved.call_args[0][0].name == scheduler.context.name
    assert reservations_approved.call_args[0][1][0].token == token

    reservations_approved.reset_mock()
    reservations_denied.reset_mock()

    # remove the reservation and deny the next one
    scheduler.remove_reservation(token)
    assert reservations_removed.called
    assert reservations_removed.call_args[0][0].name == scheduler.context.name

    token = scheduler.reserve(u'test@example.org', dates)
    assert reservations_made.called
    assert reservations_made.call_args[0][0].name == scheduler.context.name

    scheduler.deny_reservation(token)

    assert not reservations_approved.called
    assert reservations_denied.call_args[0][0].name == scheduler.context.name
    assert reservations_denied.called
    assert reservations_denied.call_args[0][1][0].token == token


def test_data_coding(scheduler):
    """ Make sure that reservation data stored in the database is returned
    without any alterations after encoding/decoding it to and from JSON.

    """
    data = {
        'index': 1,
        'name': 'record',
        'date': datetime(2014, 1, 1, 14, 0),
        'dates': [
            datetime(2014, 1, 1, 14, 0),
            datetime(2014, 1, 1, 14, 0),
            datetime(2014, 1, 1, 14, 0),
            {
                'str': [
                    datetime(2014, 1, 1, 14, 0),
                ],
                u'unicode': datetime(2014, 1, 1, 14, 0)
            }
        ],
        'nothing': None
    }
    data['nested'] = list(map(copy, (data, data)))

    start = datetime(2014, 1, 30, 15, 0)
    end = datetime(2014, 1, 30, 19, 0)

    # this won't work as json doesn't do datetimes by default
    with pytest.raises(StatementError):
        scheduler.allocate((start, end), data=data)

    scheduler.rollback()

    # luckily we can provide a better json implementation
    import jsonpickle
    from libres.context.session import SessionProvider

    def session_provider(context):
        return SessionProvider(context.get_setting('dsn'), engine_config=dict(
            json_serializer=jsonpickle.encode,
            json_deserializer=jsonpickle.decode
        ))

    # setting the service again will get rid of the existing cached value
    scheduler.context.set_service(
        'session_provider', session_provider, cache=True
    )

    scheduler.allocate((start, end), data=data)
    scheduler.commit()

    assert scheduler.managed_allocations().first().data == data

    scheduler.extinguish_managed_records()
    scheduler.commit()

    scheduler.allocate((start, end), data=None)
    scheduler.commit()

    assert scheduler.managed_allocations().first().data is None


def test_no_reservations_to_confirm(scheduler):
    start = datetime(2014, 3, 25, 14, 0)
    end = datetime(2014, 3, 25, 16, 0)
    dates = (start, end)

    session_id = new_uuid()

    scheduler.allocate(dates, approve_manually=False)
    scheduler.reserve(u'test@example.org', dates, session_id=session_id)

    # note the new session_id
    with pytest.raises(errors.NoReservationsToConfirm):
        scheduler.queries.confirm_reservations_for_session(
            session_id=new_uuid()
        )


def test_search_allocations(scheduler):
    start = datetime(2014, 8, 3, 13, 0)
    end = datetime(2014, 8, 3, 15, 0)
    daterange = (start, end)
    maxrange = (sedate.mindatetime, sedate.maxdatetime)

    # test empty
    assert len(scheduler.search_allocations(*daterange)) == 0
    assert len(scheduler.search_allocations(*maxrange)) == 0

    # test matching
    scheduler.allocate(daterange, quota_limit=2, quota=4)
    scheduler.commit()

    assert len(scheduler.search_allocations(*maxrange)) == 1
    assert len(scheduler.search_allocations(*daterange)) == 1

    # test overlapping
    adjusted = (start - timedelta(hours=1), end - timedelta(hours=1))
    assert len(scheduler.search_allocations(*adjusted)) == 1
    adjusted = (start - timedelta(hours=2), end - timedelta(minutes=59))
    assert len(scheduler.search_allocations(*adjusted)) == 1
    adjusted = (start - timedelta(hours=2), end - timedelta(hours=2))
    assert len(scheduler.search_allocations(*adjusted)) == 0

    # test days
    assert len(scheduler.search_allocations(*daterange, days=['su'])) == 1
    assert len(scheduler.search_allocations(*daterange, days=['mo'])) == 0

    # make sure the exposure is taken into account..
    class MockExposure(object):

        def __init__(self, return_value):
            self.return_value = return_value

        def is_allocation_exposed(self, allocation):
            return self.return_value

    scheduler.context.set_service('exposure', lambda ctx: MockExposure(False))
    scheduler.clear_cache()
    assert len(scheduler.search_allocations(*daterange)) == 0

    scheduler.context.set_service('exposure', lambda ctx: MockExposure(True))
    scheduler.clear_cache()
    assert len(scheduler.search_allocations(*daterange)) == 1

    # test available only
    assert len(scheduler.search_allocations(
        *daterange, available_only=True)) == 1

    for i in range(0, 4):
        scheduler.approve_reservations(
            scheduler.reserve(u'test@example.org', daterange)
        )
        scheduler.commit()

    assert len(scheduler.search_allocations(
        *daterange, available_only=True)) == 0

    # test minspots (takes quota_limit into account)
    scheduler.availability = Mock(return_value=100.0)
    assert len(scheduler.search_allocations(*daterange, minspots=1)) == 1
    assert len(scheduler.search_allocations(*daterange, minspots=2)) == 1
    assert len(scheduler.search_allocations(*daterange, minspots=3)) == 0

    scheduler.availability = Mock(return_value=50.0)
    assert len(scheduler.search_allocations(*daterange, minspots=1)) == 1
    assert len(scheduler.search_allocations(*daterange, minspots=2)) == 1
    assert len(scheduler.search_allocations(*daterange, minspots=3)) == 0

    scheduler.availability = Mock(return_value=25.0)
    assert len(scheduler.search_allocations(*daterange, minspots=1)) == 1
    assert len(scheduler.search_allocations(*daterange, minspots=2)) == 0
    assert len(scheduler.search_allocations(*daterange, minspots=3)) == 0

    scheduler.availability = Mock(return_value=0.0)
    assert len(scheduler.search_allocations(*daterange, minspots=1)) == 0
    assert len(scheduler.search_allocations(*daterange, minspots=2)) == 0
    assert len(scheduler.search_allocations(*daterange, minspots=3)) == 0


def test_search_allocation_groups(scheduler):
    s1, e1 = datetime(2014, 8, 3, 13, 0), datetime(2014, 8, 3, 15, 0)
    s2, e2 = datetime(2014, 8, 4, 13, 0), datetime(2014, 8, 4, 15, 0)

    scheduler.allocate([(s1, e1), (s2, e2)], grouped=True)
    scheduler.commit()

    assert len(scheduler.search_allocations(s1, e1, strict=True)) == 1
    assert len(scheduler.search_allocations(s2, e2, strict=True)) == 1

    assert len(scheduler.search_allocations(s1, e1, strict=False)) == 2
    assert len(scheduler.search_allocations(s2, e2, strict=False)) == 2

    assert len(scheduler.search_allocations(s1, e2)) == 2

    assert len(scheduler.search_allocations(s1, e2, groups='yes')) == 2
    assert len(scheduler.search_allocations(s1, e2, groups='no')) == 0


def test_search_whole_day_regression(scheduler):
    # https://github.com/seantis/seantis.reservation/issues/162
    s, e = datetime(2014, 8, 18, 0, 0), datetime(2014, 8, 18, 0, 0)

    scheduler.allocate((s, e), whole_day=True, partly_available=True)
    scheduler.approve_reservations(
        scheduler.reserve(
            u'test@example.org', (
                datetime(2014, 8, 18, 10, 0), datetime(2014, 8, 18, 11, 0)
            )
        )
    )
    scheduler.commit()

    # the error only manifests itself if the search is limited to a time
    # before the first reserved slot
    search_result = scheduler.search_allocations(
        datetime(2014, 8, 18, 8, 0),
        datetime(2014, 8, 18, 9, 0),
        available_only=True
    )

    assert len(search_result) == 1


def test_remove_reservation_from_session(scheduler):
    dates = (datetime(2014, 11, 26, 13, 0), datetime(2014, 11, 26, 14))
    scheduler.allocate(dates)

    sessions = [new_uuid(), new_uuid()]
    tokens = [
        scheduler.reserve(u'test@example.com', dates, session_id=sessions[0]),
        scheduler.reserve(u'test@example.com', dates, session_id=sessions[1])
    ]

    scheduler.commit()

    assert scheduler.queries.reservations_by_session(sessions[0]).count() == 1
    assert scheduler.queries.reservations_by_session(sessions[1]).count() == 1

    scheduler.queries.remove_reservation_from_session(sessions[0], tokens[0])
    scheduler.commit()

    assert scheduler.queries.reservations_by_session(sessions[0]).count() == 0
    assert scheduler.queries.reservations_by_session(sessions[1]).count() == 1


def test_availability_by_day(scheduler):
    dates = (datetime(2014, 11, 26, 13, 0), datetime(2014, 11, 26, 14))

    allocation = scheduler.allocate(dates)[0]
    scheduler.approve_reservations(
        scheduler.reserve(u'test@example.com', dates)
    )
    scheduler.commit()

    sc2 = scheduler.clone()
    sc2.name = 'clone'

    sc2.allocate(dates)
    sc2.commit()

    # we need the timezone for this
    dates = (allocation.start, allocation.end)

    resources = (sc2.resource, )
    days = scheduler.queries.availability_by_day(*dates, resources=resources)
    assert days[dates[0].date()][0] == 100.0

    resources = (scheduler.resource, sc2.resource)
    days = scheduler.queries.availability_by_day(*dates, resources=resources)
    assert days[dates[0].date()][0] == 50.0

    resources = (scheduler.resource, )
    days = scheduler.queries.availability_by_day(*dates, resources=resources)
    assert days[dates[0].date()][0] == 0.00

    sc2.extinguish_managed_records()
    sc2.commit()


def test_remove_unused_allocations(scheduler):

    # create one allocation with a pending reservation
    daterange = (datetime(2013, 12, 3, 13, 0), datetime(2013, 12, 3, 15, 0))
    scheduler.allocate(daterange)
    scheduler.reserve(u'test@example.org', daterange)
    scheduler.commit()

    # create one allocation with a finished reservation
    daterange = (datetime(2014, 12, 3, 13, 0), datetime(2014, 12, 3, 15, 0))
    scheduler.allocate(daterange)
    scheduler.approve_reservations(
        scheduler.reserve(u'test@example.org', daterange)
    )
    scheduler.commit()

    # create a group of allocations with a pending reservation
    daterange = [
        (datetime(2015, 12, 3, 13, 0), datetime(2015, 12, 3, 15, 0)),
        (datetime(2015, 12, 4, 13, 0), datetime(2015, 12, 4, 15, 0))
    ]
    scheduler.allocate(daterange, grouped=True)
    scheduler.reserve(u'test@example.org', daterange)
    scheduler.commit()

    # create one unused allocation
    daterange = (datetime(2016, 12, 3, 13, 0), datetime(2016, 12, 3, 15, 0))
    scheduler.allocate(daterange)
    scheduler.commit()

    # create two unused allocations in a group
    daterange = [
        (datetime(2017, 12, 3, 13, 0), datetime(2017, 12, 3, 15, 0)),
        (datetime(2017, 12, 4, 13, 0), datetime(2017, 12, 4, 15, 0))
    ]
    scheduler.allocate(daterange)
    scheduler.commit()

    # only the unused allocation should be removed
    assert scheduler.managed_allocations().count() == 7
    deleted = scheduler.remove_unused_allocations(
        date(2013, 1, 1), date(2016, 12, 31))

    assert deleted == 1
    assert scheduler.managed_allocations().count() == 6

    # if a grouped allocation is touched, the whole group must be inside
    # the date scope for it to be deleted
    deleted = scheduler.remove_unused_allocations(
        date(2017, 12, 3), date(2017, 12, 3))

    assert deleted == 0
    assert scheduler.managed_allocations().count() == 6

    deleted = scheduler.remove_unused_allocations(
        date(2017, 12, 4), date(2017, 12, 4))

    assert deleted == 0
    assert scheduler.managed_allocations().count() == 6

    deleted = scheduler.remove_unused_allocations(
        date(2000, 1, 1), date(2020, 1, 1))

    assert deleted == 2
    assert scheduler.managed_allocations().count() == 4
