import pytest

from libres.modules import errors
from libres.context.session import SessionProvider
from libres.db.models import Allocation


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
