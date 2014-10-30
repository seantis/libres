import pytest
import uuid

from testing.postgresql import Postgresql

from libres import new_scheduler


def new_test_scheduler(dsn, context=None, name=None):
    return new_scheduler(
        context=context or uuid.uuid4().hex,
        name=name or uuid.uuid4().hex,
        timezone='Europe/Zurich',
        settings={
            'settings.dsn': dsn
        }
    )


@pytest.yield_fixture(scope="function")
def scheduler(request, dsn):

    if 'scheduler_context' in request.funcargnames:
        context = request.getfuncargvalue('scheduler_context')
    else:
        context = None

    if 'scheduler_name' in request.funcargnames:
        name = request.getfuncargvalue('scheduler_context')
    else:
        name = None

    scheduler = new_test_scheduler(dsn, context, name)

    yield scheduler

    scheduler.extinguish_managed_records()
    scheduler.commit()

    scheduler.close()


@pytest.yield_fixture(scope="session")
def dsn():
    postgres = Postgresql()

    scheduler = new_test_scheduler(postgres.url())
    scheduler.setup_database()
    scheduler.commit()

    yield postgres.url()

    scheduler.close()

    postgres.stop()
