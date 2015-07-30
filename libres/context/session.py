import re

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
        """ Returns the postgres version in a tuple with the first value being
        the major version, the second being the minor version.

        Uses it's own connection to be independent from any session.

        """
        assert 'postgres' in dsn, "Not a postgres database"

        engine = create_engine(dsn)
        version = engine.execute('select version()').fetchone()[0]
        engine.dispose()

        version = re.findall('PostgreSQL (.*?) on', version)[0]
        return [int(fragment) for fragment in version.split('.')][:2]

    def assert_valid_postgres_version(self, dsn):
        major, minor = self.get_postgres_version(dsn)

        assert (major >= 9 and minor >= 1) or (major >= 10), \
            "PostgreSQL 9.1+ is required. Your version is {}.{}".format(
                major, minor)

        return dsn
