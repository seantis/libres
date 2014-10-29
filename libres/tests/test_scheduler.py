from datetime import datetime
from libres import new_scheduler


def test_managed_allocations(scheduler):

    start = datetime(2014, 4, 4, 14, 0)
    end = datetime(2014, 4, 4, 15, 0)
    timezone = 'Europe/Zurich'

    allocations = scheduler.allocate((start, end), timezone)
    assert len(allocations) == 1

    scheduler.commit()

    # create a second scheduler using the same context
    s2 = new_scheduler(
        scheduler.context.name,
        'second scheduler'
    )

    allocations = s2.allocate((start, end), timezone)
    assert len(allocations) == 1

    s2.commit()

    assert scheduler.managed_allocations().count() == 1
    assert s2.managed_allocations().count() == 1
