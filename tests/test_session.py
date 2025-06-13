from __future__ import annotations

import libres
import time

from datetime import datetime
from libres.context.session import SessionProvider
from libres.db.models import Allocation
from libres.db.scheduler import Scheduler
from psycopg2.extensions import TransactionRollbackError
from threading import Thread
from uuid import uuid4 as new_uuid


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Callable


class SessionId(Thread):
    def __init__(self, dsn: str) -> None:
        Thread.__init__(self)
        self.session_id: int | None = None
        self.dsn = dsn

    def run(self) -> None:
        context = libres.registry.register_context(str(id(self)))
        context.set_setting('dsn', self.dsn)
        scheduler = Scheduler(context, 'threading', 'UTC')
        self.session_id = id(scheduler.session)

        # make sure the thread runs long enough for test_collision to
        # have both threads running at the same time, since the docs states:
        # "Two objects with non-overlapping lifetimes may have the same
        # id() value."
        time.sleep(0.1)


class ExceptionThread(Thread):
    def __init__(
        self,
        call: Callable[[], object],
        commit: Callable[[], object] | None
    ) -> None:
        Thread.__init__(self)
        self.call = call
        self.exception: Exception | None = None
        self.commit = commit

    def run(self) -> None:
        try:
            self.call()
            import time
            time.sleep(1)
            if self.commit is not None:
                self.commit()
        except Exception as e:
            self.exception = e


def test_stop_unused_session(dsn: str) -> None:
    provider = SessionProvider(dsn)
    provider.stop_service()  # should not throw any exceptions


def test_sessionstore(dsn: str) -> None:
    t1 = SessionId(dsn)
    t2 = SessionId(dsn)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    assert t1.session_id is not None
    assert t2.session_id is not None
    assert t1.session_id != t2.session_id


def test_collision(scheduler: Scheduler) -> None:

    scheduler.allocate(
        (datetime(2014, 11, 27, 12), datetime(2014, 11, 27, 13))
    )
    scheduler.commit()

    def change_allocation(scheduler: Scheduler) -> None:
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

    def is_rollback(ex: Exception | None) -> bool:
        return isinstance(getattr(ex, 'orig', None), TransactionRollbackError)

    def is_nothing(ex: Exception | None) -> bool:
        return not is_rollback(ex)

    rollbacks = list(filter(is_rollback, exceptions))
    updates = list(filter(is_nothing, exceptions))

    assert len(rollbacks) == 1
    assert len(updates) == 1


def test_non_collision(scheduler: Scheduler) -> None:

    scheduler.allocate(
        (datetime(2014, 11, 27, 12), datetime(2014, 11, 27, 13))
    )
    scheduler.commit()

    def change_allocation(scheduler: Scheduler) -> None:
        a = scheduler.session.query(Allocation).one()
        a.group = new_uuid()

    def read_allocation(scheduler: Scheduler) -> None:
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

    def is_rollback(ex: Exception | None) -> bool:
        return isinstance(getattr(ex, 'orig', None), TransactionRollbackError)

    rollbacks = list(filter(is_rollback, exceptions))
    assert len(rollbacks) == 0
