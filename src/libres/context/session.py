from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import scoped_session, sessionmaker

from libres.context.core import StoppableService


from typing import Any


SERIALIZABLE = 'SERIALIZABLE'


class SessionProvider(StoppableService):
    """Global session utility. It provides a SERIALIZABLE session to libres.
    If you want to override this provider, be sure to set the isolation_level
    to SERIALIZABLE as well.

    If you don't do that, libres might run into errors as it assumes and tests
    against SERIALIZABLE connections!

    """

    def __init__(
        self,
        dsn: str,
        engine_config: dict[str, Any] | None = None,
        session_config: dict[str, Any] | None = None
    ):
        self.assert_valid_postgres_version(dsn)
        self.dsn = dsn

        self.engine = create_engine(
            dsn, poolclass=QueuePool, pool_size=5, max_overflow=5,
            isolation_level=SERIALIZABLE,
            **(engine_config or {})
        )

        self.session = scoped_session(sessionmaker(
            bind=self.engine, **(session_config or {})
        ))

    def stop_service(self) -> None:
        """ Called by the libres context when the session provider is being
        discarded (only in testing).

        This makes sure that replacing the session provider on the context
        doesn't leave behind any idle connections.

        """

        self.session().close()
        self.engine.raw_connection().invalidate()
        self.engine.dispose()

    def get_postgres_version(self, dsn: str) -> tuple[str, int]:
        """ Returns the postgres version as a tuple (string, integer).

        Uses it's own connection to be independent from any session.

        """
        assert 'postgres' in dsn, 'Not a postgres database'

        query = """
            SELECT current_setting('server_version'),
                   current_setting('server_version_num')
        """

        engine = create_engine(dsn)

        try:
            result = engine.execute(query).first()
            assert result is not None
            version, number = result
            return version, int(number)
        finally:
            engine.dispose()

    def assert_valid_postgres_version(self, dsn: str) -> str:
        v, n = self.get_postgres_version(dsn)

        if n < 90100:
            raise RuntimeError(f'PostgreSQL 9.1+ is required, got {v}')

        return dsn
