import pytest

from libres.context.session import SessionProvider
from libres.db.models import Allocation
from libres.db.scheduler import Scheduler
from libres.modules import errors
from threading import Thread


def test_guard_flush(dsn):
    provider = SessionProvider(dsn)
    provider.use_readonly()

    session = provider.session()
    session.add(Allocation())

    with pytest.raises(errors.ModifiedReadOnlySession):
        session.flush()

    session.rollback()


def test_guard_execute(dsn):
    provider = SessionProvider(dsn)
    provider.use_readonly()

    allocation = Allocation()
    session = provider.session()

    with pytest.raises(errors.ModifiedReadOnlySession):
        session.execute(allocation.__table__.insert(), {"id": 7})

    session.rollback()


def test_sessionstore(dsn):

    class SessionIds(Thread):
        def __init__(self):
            Thread.__init__(self)
            self.serial_id = None
            self.readonly_id = None

        def run(self):
            scheduler = Scheduler('tests', 'threading', 'UTC', settings={
                'settings.dsn': dsn
            })
            self.readonly_id = id(scheduler.context.readonly_session)
            self.serial_id = id(scheduler.context.serial_session)

    t1 = SessionIds()
    t2 = SessionIds()

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert t1.readonly_id is not None
    assert t1.serial_id is not None
    assert t2.readonly_id is not None
    assert t2.serial_id is not None
    assert t1.readonly_id != t2.readonly_id
    assert t1.serial_id != t2.serial_id
