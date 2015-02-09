import re
import threading
import functools

from sqlalchemy.sql.dml import UpdateBase
from sqlalchemy import create_engine
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy import event

from libres.context.core import StoppableService
from libres.modules import errors

SERIALIZABLE = 'SERIALIZABLE'
READ_COMMITTED = 'READ_COMMITTED'


class SessionStore(object):
    """ Holds the read-commited and serializable session. """

    def __init__(self, dsn, engine_config, session_config):
        self.readonly = self.create_session(
            READ_COMMITTED, dsn, engine_config, session_config
        )
        self.serial = self.create_session(
            SERIALIZABLE, dsn, engine_config, session_config
        )
        self.current = self.readonly
        self.dsn = dsn

    @staticmethod
    def create_session(isolation_level, dsn, engine_config, session_config):
        """Creates a session with the given isolation level.

        If the isolation level is serializable (writeable) a hook is created
        which will mark the session as used once it is flushed, as unused when
        the session is commited or rolledback.

        If the isolation level is read commited (readonly) a hook is created
        which will ensure that the readonly session cannot be used to flush
        changes to the database by raising ModifiedReadOnlySession if
        there are detected changes about to be flushed.

        """

        # I don't see how overriding the following keys would end well
        assert 'isolation_level' not in engine_config
        assert 'poolclass' not in engine_config
        assert 'bind' not in session_config

        engine = create_engine(
            dsn,
            poolclass=SingletonThreadPool,
            isolation_level=isolation_level,
            **engine_config
        )

        session = scoped_session(sessionmaker(
            bind=engine, autocommit=False, autoflush=True, **session_config
        ))

        if isolation_level == READ_COMMITTED:
            # TODO I suspect that I can remove 'guard_flush' in favor of
            # 'guard_execute'. They basically do the same thing, but
            # 'guard_execute' is simpler and faster (though it will be
            # called more often). Not to mention that it also catches
            # statements created directly without the help of the orm.
            #
            # Once all tests are migrated from seantis.reservation it's
            # worth a try.
            def guard_flush(session, *args):
                changelists = [session.dirty, session.deleted, session.new]

                # sum up the len of all changelists
                if sum(map(len, changelists)):
                    raise errors.ModifiedReadOnlySession

            def guard_execute(conn, clauseelement, multiparams, params):
                if isinstance(clauseelement, UpdateBase):
                    raise errors.ModifiedReadOnlySession

            event.listen(session, 'before_flush', guard_flush)
            event.listen(session.bind, 'before_execute', guard_execute)

        if isolation_level == SERIALIZABLE:

            def reset_serial(session, *args):
                session._was_used = False

            def mark_serial(session, *args):
                session._was_used = True

            event.listen(session, 'after_commit', reset_serial)
            event.listen(session, 'after_rollback', reset_serial)
            event.listen(session, 'after_soft_rollback', reset_serial)
            event.listen(session, 'after_flush', mark_serial)

        return session


class SessionProvider(StoppableService):
    """Global session utility. It wraps two global sessions through which
    all database interaction (should) be flowing.

    As a global utility this object is present only once per Zope instance,
    so it needs to be aware of different threads.
    """

    def __init__(self, dsn, engine_config={}, session_config={}):
        self._threadstore = threading.local()
        self.dsn = dsn
        self.engine_config = engine_config
        self.session_config = session_config

    def stop_service(self):
        """ Called by the libres context when the session provider is being
        discarded.

        This makes sure that replacing the session provider on the context
        doesn't leave behind any idle connections.

        """
        if not hasattr(self._threadstore, 'sessions'):
            return

        engines = {}

        for dsn, session in self._threadstore.sessions.items():
            engines[dsn] = session.serial.bind

            session.serial.close()
            session.readonly.close()

        for engine in engines.values():
            engine.raw_connection().invalidate()
            engine.dispose()

    @property
    def sessionstore(self):
        """Returns the current sessionstore which will be populated with
        sessions if they are not yet present.

        """
        if not hasattr(self._threadstore, 'sessions'):
            self._threadstore.sessions = {}

        if self.dsn not in self._threadstore.sessions:
            self.assert_dsn(self.dsn)
            self._threadstore.sessions[self.dsn] = SessionStore(
                self.dsn,
                self.engine_config,
                self.session_config
            )

        return self._threadstore.sessions[self.dsn]

    @property
    def is_serial(self):
        return self.sessionstore.current is self.sessionstore.serial

    @property
    def is_readonly(self):
        return self.sessionstore.current is self.sessionstore.readonly

    def is_serial_dirty(self, reset=False):
        """Returns true if the serial session was used (flushed). False if
        it was reset (rollback, commited).

        The idea is to indicate when the serial session has access to
        uncommited data which will be invisible to the readonly session.

        """
        serial = self.sessionstore.serial.registry()
        dirty = hasattr(serial, '_was_used') and serial._was_used

        if dirty and reset:
            serial._was_used = False

        return dirty

    def session(self):
        """ Return the current session. Raises DirtyReadOnlySession if the
        session to be returned is read only and the serial session was used.

        The readonly session at this point would not see uncommitted changes.
        The serial session would, but it should not be used for that if
        possible, since every read on the serial session spreads the possible
        locks within the postgres database.

        If information is needed after using the serial session, either cache
        what you need before flushing (if you need stuff which is only in the
        serial session at the time). Or use the read session before using the
        serial session (which leads to the same result in a way, but is
        explicit).

        """
        if self.is_readonly and self.is_serial_dirty(reset=True):
            raise errors.DirtyReadOnlySession

        return self.sessionstore.current

    def use_readonly(self):
        self.sessionstore.current = self.sessionstore.readonly
        return self.sessionstore.current

    def use_serial(self):
        self.sessionstore.current = self.sessionstore.serial
        return self.sessionstore.current

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

    def assert_dsn(self, dsn):
        major, minor = self.get_postgres_version(dsn)

        assert (major >= 9 and minor >= 1) or (major >= 10), \
            "PostgreSQL 9.1+ is required. Your version is {}.{}".format(
                major, minor)

        return dsn


def serialized(fn):
    """ Wrapper function which wraps any function with a serial session.
    All methods called by this wrapped function will uuse the serial session.

    To be able to do this, serialized has to have access to the session
    provider. It is assumed that the first argument passed to the wrapped
    function has a session_provider attribute.

    The :class:`Serializable` class already provides that. Objects inheriting
    from that class can therefore use `@serializable` for their methods
    (because `self` is the first argument).

    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        session_provider = args[0].session_provider

        current = session_provider.sessionstore.current
        serial = session_provider.use_serial()

        try:
            result = fn(*args, **kwargs)
            serial.flush()
            serial.expire_all()
            return result
        finally:
            session_provider.sessionstore.current = current

    return wrapper


class Serializable(object):
    """ Provides the link between context and session, as well as a few
    methods to easily work with the session.

    A class wanting to work with @serialized should inherit from this.
    Such an inherited class should either provide self.context, returning
    the libres context used, or self.session_provider like below.

    """

    @property
    def session_provider(self):
        return self.context.get_service('session_provider')

    @property
    def session(self):
        """ Returns the current session. This can be the read-only or the
        serialized session, depending on where it is called from.

        """
        return self.session_provider.session()

    @property
    def serial_session(self):
        return self.session_provider.sessionstore.serial

    @property
    def readonly_session(self):
        return self.session_provider.sessionstore.readonly

    def close(self):
        """ Closes all known sessions/binds. """
        self.serial_session.close()
        self.readonly_session.close()

    @property
    def begin_nested(self):
        return self.serial_session.begin_nested

    def commit(self):
        self.readonly_session.expire_all()
        return self.serial_session.commit()

    def rollback(self):
        self.readonly_session.expire_all()
        return self.serial_session.rollback()
