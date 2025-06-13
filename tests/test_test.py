from __future__ import annotations

import pytest

from datetime import datetime
from libres.db.models import Allocation


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from libres.db.scheduler import Scheduler


@pytest.mark.parametrize('execution_number', range(2))
@pytest.mark.parametrize('scheduler_context', ['test'])
@pytest.mark.parametrize('scheduler_name', ['test'])
def test_independence(
    scheduler: Scheduler,
    execution_number: int,
    scheduler_context: str,
    scheduler_name: str
) -> None:
    """ Test the independence of tests. This test is run twice with the exact
    same records written. If any records remain after a single test run, the
    second run of this test fails.

    This ensures proper separation between tests.

    """
    assert scheduler.context.name == scheduler_context
    assert scheduler.name == scheduler_name

    scheduler.allocate(
        (datetime(2014, 4, 4, 14, 0), datetime(2014, 4, 4, 15, 0))
    )
    scheduler.commit()

    # note, if this fails for you you probably created your own
    # scheduler, or cloned an existing one -> those schedulers are for you
    # to clean up, by calling scheduler.extinguish_managed_records followed
    # by a commit!
    assert scheduler.managed_allocations().count() == 1
    assert scheduler.session.query(Allocation).count() == 1
