from datetime import datetime


def test_managed_allocations(scheduler):

    start = datetime(2014, 4, 4, 14, 0)
    end = datetime(2014, 4, 4, 15, 0)
    timezone = 'Europe/Zurich'

    allocations = scheduler.allocate((start, end), timezone)
    assert len(allocations) == 1

    scheduler.commit()

    # create a second scheduler using the same context, but with a different
    # name, which should result in a different set of managed allocations
    s2 = scheduler.clone()
    assert s2.managed_allocations().count() == 1

    s2.name = 'clone'
    assert s2.managed_allocations().count() == 0

    s2.allocate((start, end), timezone)
    s2.commit()

    assert s2.managed_allocations().count() == 1

    assert scheduler.managed_allocations().count() == 1
    assert s2.managed_allocations().count() == 1


def test_reserve(scheduler):

    scheduler.default_timezone = 'Europe/Zurich'
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

    # # try to illegally move the slot
    # with pytest.raises(errors.AffectedReservationError):
    #     scheduler.move_allocation(
    #         master_id=allocation.id,
    #         new_start=datetime(2011, 1, 1, 15, 30),
    #         new_end=datetime(2011, 1, 1, 16),
    #     )

    # assert len(allocation.free_slots()) == 2

    # # actually move the slot
    # scheduler.move_allocation(
    #     master_id=allocation.id,
    #     new_start=datetime(2011, 1, 1, 15),
    #     new_end=datetime(2011, 1, 1, 15, 30)
    # )

    # # there should be fewer slots now
    # assert len(allocation.free_slots()) == 0

    # # remove the reservation
    # scheduler.remove_reservation(token)
    # assert len(allocation.free_slots()) == 2
