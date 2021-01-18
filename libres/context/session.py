from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import scoped_session, sessionmaker

from libres.context.core import StoppableService


SERIALIZABLE = 'SERIALIZABLE'


class SessionProvider(StoppableService):
    """Global session utility. It provides a SERIALIZABLE session to libres.
    If you want to override this provider, be sure to set the isolation_level
    to SERIALIZABLE as well.

    If you don't do that, libres might run into errors as it assumes and tests
    against SERIALIZABLE connections!

    """

    def __init__(self, dsn, engine_config={}, session_config={}):
        self.assert_valid_postgres_version(dsn)
        self.dsn = dsn

        self.engine = create_engine(
            dsn, poolclass=QueuePool, pool_size=5, max_overflow=5,
            isolation_level=SERIALIZABLE,
            **engine_config
        )

        self.session = scoped_session(sessionmaker(
            bind=self.engine, **session_config
        ))

    def stop_service(self):
        """ Called by the libres context when the session provider is being
        discarded (only in testing).

        This makes sure that replacing the session provider on the context
        doesn't leave behind any idle connections.

        """

        self.session().close()
        self.engine.raw_connection().invalidate()
        self.engine.dispose()

    def get_postgres_version(self, dsn):
        """ Returns the postgres version as a tuple (string, integer).

        Uses it's own connection to be independent from any session.

        """
        assert 'postgres' in dsn, "Not a postgres database"

        query = """
            SELECT current_setting('server_version'),
                   current_setting('server_version_num')
        """

        engine = create_engine(dsn)

        try:
            version, number = engine.execute(query).first()
            return version, int(number)
        finally:
            engine.dispose()

    def assert_valid_postgres_version(self, dsn):
        v, n = self.get_postgres_version(dsn)

        if n < 90100:
            raise RuntimeError("PostgreSQL 9.1+ is required, got {}".format(v))

        return dsn
