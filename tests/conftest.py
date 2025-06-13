from __future__ import annotations

import pytest
from _pytest.fixtures import FixtureLookupError

from libres import new_scheduler, registry
# FIXME: Switch to pytest-postgresql, testing.postgresql is unmaintained
from testing.postgresql import Postgresql  # type: ignore[import-untyped]
from uuid import uuid4 as new_uuid


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Generator
    from libres.db.scheduler import Scheduler


def new_test_scheduler(
    dsn: str,
    context_name: str | None = None,
    scheduler_name: str | None = None
) -> Scheduler:

    context_name = context_name or new_uuid().hex
    scheduler_name = scheduler_name or new_uuid().hex

    context = registry.register_context(context_name, replace=True)
    context.set_setting('dsn', dsn)

    return new_scheduler(
        context=context,
        name=scheduler_name,
        timezone='Europe/Zurich'
    )


@pytest.fixture
def scheduler(
    request: pytest.FixtureRequest,
    dsn: str
) -> Generator[Scheduler, None, None]:

    # clear the events before each test
    from libres.modules import events
    for event in (e for e in dir(events) if e.startswith('on_')):
        del getattr(events, event)[:]

    try:
        context = request.getfixturevalue('scheduler_context')
    except FixtureLookupError:
        context = None

    try:
        name = request.getfixturevalue('scheduler_context')
    except FixtureLookupError:
        name = None

    scheduler = new_test_scheduler(dsn, context, name)

    yield scheduler

    scheduler.rollback()
    scheduler.extinguish_managed_records()
    scheduler.commit()
    scheduler.close()
    scheduler.session_provider.stop_service()


@pytest.fixture(scope="session")
def dsn() -> Generator[str, None, None]:
    postgres = Postgresql()

    scheduler = new_test_scheduler(postgres.url())
    scheduler.setup_database()
    scheduler.commit()

    yield postgres.url()

    scheduler.close()

    postgres.stop()
