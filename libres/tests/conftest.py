import pytest
import uuid

from testing.postgresql import Postgresql

from libres import new_scheduler
from libres.db.models import ORMBase


def new_random_scheduler(dsn):
    return new_scheduler(
        context=uuid.uuid4().hex,
        name=uuid.uuid4().hex,
        settings={
            'settings.dsn': dsn
        }
    )


@pytest.yield_fixture(scope="function")
def scheduler(dsn):

    scheduler = new_random_scheduler(dsn)

    yield scheduler

    scheduler.dispose()


@pytest.yield_fixture(scope="session")
def dsn():
    postgres = Postgresql()

    scheduler = new_random_scheduler(postgres.url())
    scheduler.setup_database()
    scheduler.commit()

    yield postgres.url()

    scheduler.context.readonly_session.close()
    ORMBase.metadata.drop_all(scheduler.context.serial_session.bind)
    postgres.stop()
