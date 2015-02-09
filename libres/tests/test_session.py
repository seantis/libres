import libres
import pytest
import time

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
        context = libres.registry.register_context(id(self))
        context.set_setting('dsn', self.dsn)
        scheduler = Scheduler(context, 'threading', 'UTC')
        self.readonly_id = id(scheduler.readonly_session)
        self.serial_id = id(scheduler.serial_session)

        # make sure the thread runs long enough for test_collision to
        # have both threads running at the same time, since the docs states:
        # "Two objects with non-overlapping lifetimes may have the same
        # id() value."
        time.sleep(0.1)


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


def test_stop_unused_session(dsn):
    provider = SessionProvider(dsn)
    provider.stop_service()  # should not throw any exceptions


def test_session_switch(dsn):
    provider = SessionProvider(dsn)
    assert provider.is_readonly

    provider.use_serial()
    assert provider.is_serial

    provider.use_readonly()
    assert provider.is_readonly


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

    def is_rollback(ex):
        return ex and isinstance(ex.orig, TransactionRollbackError)

    def is_nothing(ex):
        return not is_rollback(ex)

    rollbacks = list(filter(is_rollback, exceptions))
    updates = list(filter(is_nothing, exceptions))

    assert len(rollbacks) == 1
    assert len(updates) == 1


def test_non_collision(scheduler):

    scheduler.allocate(
        (datetime(2014, 11, 27, 12), datetime(2014, 11, 27, 13))
    )
    scheduler.commit()

    @serialized
    def change_allocation(scheduler):
        a = scheduler.session.query(Allocation).one()
        a.group = new_uuid()

    @serialized
    def read_allocation(scheduler):
        scheduler.session.query(Allocation).one()

    t1 = ExceptionThread(
        lambda: change_allocation(scheduler), scheduler.commit
    )
    t2 = ExceptionThread(
        lambda: read_allocation(scheduler), scheduler.rollback
    )

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    exceptions = (t1.exception, t2.exception)

    def is_rollback(ex):
        return ex and isinstance(ex.orig, TransactionRollbackError)

    rollbacks = list(filter(is_rollback, exceptions))
    assert len(rollbacks) == 0
