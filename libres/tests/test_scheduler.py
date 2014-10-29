from datetime import datetime


def test_managed_allocations(scheduler):

    start = datetime(2014, 4, 4, 14, 0)
    end = datetime(2014, 4, 4, 15, 0)
    timezone = 'Europe/Zurich'

    allocations = scheduler.allocate((start, end), timezone)
    assert len(allocations) == 1

    scheduler.commit()

    # # create a second scheduler with the same context
    # import ipdb; ipdb.set_trace()
    # scheduler = database.get_new_scheduler()

    # allocations = s2.allocate((start, end), timezone)
    # assert len(allocations) == 1

    # s2.commit()

    # assert s1.managed_allocations().count() == 1
    # assert s2.managed_allocations().count() == 1
