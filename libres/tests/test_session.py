import pytest

from datetime import datetime
from libres.context.session import SessionProvider, serialized
from libres.db.models import Allocation
from libres.db.scheduler import Scheduler
from libres.modules import errors
from psycopg2.extensions import TransactionRollbackError
from threading import Thread
from uuid import uuid4 as new_uuid


class SessionIds(Thread):
    def __init__(self, dsn):
        Thread.__init__(self)
        self.serial_id = None
        self.readonly_id = None
        self.dsn = dsn

    def run(self):
        scheduler = Scheduler('tests', 'threading', 'UTC', settings={
            'settings.dsn': self.dsn
        })
        self.readonly_id = id(scheduler.context.readonly_session)
        self.serial_id = id(scheduler.context.serial_session)


class ExceptionThread(Thread):
    def __init__(self, call, commit):
        Thread.__init__(self)
        self.call = call
        self.exception = None
        self.commit = commit

    def run(self):
        try:
            self.call()
            import time
            time.sleep(1)
            if self.commit is not None:
                self.commit()
        except Exception as e:
            self.exception = e


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


def test_dirty_protection(scheduler):

    id = scheduler.allocate(
        (datetime(2014, 11, 27, 12), datetime(2014, 11, 27, 13))
    )[0].id

    with pytest.raises(errors.DirtyReadOnlySession):
        scheduler.allocation_by_id(id)

    scheduler.commit()

    scheduler.allocation_by_id(id)


def test_sessionstore(dsn):
    t1 = SessionIds(dsn)
    t2 = SessionIds(dsn)

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


def test_collision(scheduler):

    scheduler.allocate(
        (datetime(2014, 11, 27, 12), datetime(2014, 11, 27, 13))
    )
    scheduler.commit()

    @serialized
    def change_allocation(scheduler):
        a = scheduler.session.query(Allocation).one()
        a.group = new_uuid()

    t1 = ExceptionThread(
        lambda: change_allocation(scheduler), scheduler.commit
    )
    t2 = ExceptionThread(
        lambda: change_allocation(scheduler), scheduler.commit
    )

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    exceptions = (t1.exception, t2.exception)

    is_rollback = lambda ex: ex and isinstance(
        ex.orig, TransactionRollbackError
    )
    is_nothing = lambda ex: not is_rollback(ex)

    rollbacks = list(filter(is_rollback, exceptions))
    updates = list(filter(is_nothing, exceptions))

    assert len(rollbacks) == 1
    assert len(updates) == 1
