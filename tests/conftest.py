import pytest
from _pytest.fixtures import FixtureLookupError

from libres import new_scheduler, registry
from testing.postgresql import Postgresql
from uuid import uuid4 as new_uuid


def new_test_scheduler(dsn, context=None, name=None):
    context = context or new_uuid().hex
    name = name or new_uuid().hex

    context = registry.register_context(context, replace=True)
    context.set_setting('dsn', dsn)

    return new_scheduler(context=context, name=name, timezone='Europe/Zurich')


@pytest.fixture(scope="function")
def scheduler(request, dsn):

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
def dsn():
    postgres = Postgresql()

    scheduler = new_test_scheduler(postgres.url())
    scheduler.setup_database()
    scheduler.commit()

    yield postgres.url()

    scheduler.close()

    postgres.stop()
