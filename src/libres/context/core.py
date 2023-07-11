import enum
import libres
import threading

from contextlib import contextmanager
from functools import cached_property

from libres.modules import errors


import typing as _t
if _t.TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.session import SessionTransaction
    from uuid import UUID

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.db.models import Allocation


class _Marker(enum.Enum):
    missing = enum.auto()
    required = enum.auto()


missing_t = _t.Literal[_Marker.missing]
required_t = _t.Literal[_Marker.required]
missing: missing_t = _Marker.missing
required: required_t = _Marker.required


class StoppableService:
    """ Services inheriting from this class have their stop_service method
    called when the service is discarded.

    Note that this only happens when a service is replaced with a new one
    and not when libres is stopped (i.e. this is *not* a deconstructor).

    """

    def stop_service(self) -> None:
        pass


class ContextServicesMixin:
    """ Provides access methods to the context's services. Expects
    the class that uses the mixin to provide self.context.

    The results are cached for performance.

    """

    context: 'Context'

    @cached_property
    def is_allocation_exposed(self) -> _t.Callable[['Allocation'], bool]:
        return self.context.get_service('exposure').is_allocation_exposed

    @cached_property
    def generate_uuid(self) -> _t.Callable[[str], 'UUID']:
        return self.context.get_service('uuid_generator')

    @cached_property
    def validate_email(self) -> _t.Callable[[str], bool]:
        return self.context.get_service('email_validator')

    def clear_cache(self) -> None:
        """ Clears the cache of the mixin. """

        try:
            del self.is_allocation_exposed
        except AttributeError:
            pass

        try:
            del self.generate_uuid
        except AttributeError:
            pass

        try:
            del self.validate_email
        except AttributeError:
            pass

    @property
    def session_provider(self) -> 'SessionProvider':
        return self.context.get_service('session_provider')

    @property
    def session(self) -> 'Session':
        """ Returns the current session. """
        return self.session_provider.session()

    def close(self) -> None:
        """ Closes the current session. """
        self.session.close()

    @property
    def begin_nested(self) -> _t.Callable[[], 'SessionTransaction']:
        return self.session.begin_nested

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


class Context:
    """ Used throughout Libres, the context holds settings like the database
    connection string and services like the json dumps/loads functions that
    should be used.

    Contexts allow consumers of the Libres library to override these settings /
    services as they wish. It also makes sure that multiple consumers of Libres
    can co-exist in a single process, as each consumer must operate on it's
    own context.

    Libres holds all contexts in libres.registry and provides a master_context.
    When a consumer registers its own context, all lookups happen on the custom
    context. If that context can provide a service or a setting, it is used.

    If the custom context can't provide a service or a setting, the
    master_context is used instead. In other words, the custom context
    inherits from the master context.

    Note that contexts not meant to be changed often. Classes talking to the
    database usually cache data form the context freely. That means basically
    that after changing the context you should get a fresh
    :class:`~libres.db.scheduler.Scheduler` instance or call
    :meth:`~.ContextServicesMixin.clear_cache`.

    A context may be registered as follows::

        from libres import registry
        my_context = registry.register_context('my_app')

    See also :class:`~libres.context.registry.Registry`

    """

    def __init__(
        self,
        name: str,
        registry: _t.Optional['Registry'] = None,
        parent: _t.Optional['Context'] = None,
        locked: bool = False
    ):
        self.name = name
        self.registry = registry or libres.registry
        self.values: _t.Dict[str, _t.Any] = {}
        self.parent = parent
        self.locked = False
        self.thread_lock = threading.RLock()

    def __repr__(self) -> str:
        return f"<Libres Context(name='{self.name}')>"

    @contextmanager
    def as_current_context(self) -> _t.Iterator[None]:
        with self.registry.context(self.name):
            yield

    def switch_to(self) -> None:
        self.registry.switch_context(self.name)

    def lock(self) -> None:
        with self.thread_lock:
            self.locked = True

    def unlock(self) -> None:
        with self.thread_lock:
            self.locked = False

    def get(self, key: str) -> _t.Union[_t.Any, missing_t]:
        if key in self.values:
            return self.values[key]
        elif self.parent:
            return self.parent.get(key)
        else:
            return missing

    def set(self, key: str, value: _t.Any) -> None:
        if self.locked:
            raise errors.ContextIsLocked

        with self.thread_lock:

            # If a value already exists it could be a stoppable service.
            # Stoppable services are called before they are stop so they
            # can clean up after themselves without having to wait for the GC.
            if isinstance(self.values.get(key), StoppableService):
                self.values[key].stop_service()

            self.values[key] = value

    def get_setting(self, name: str) -> _t.Any:
        return self.get(f'settings.{name}')

    def set_setting(self, name: str, value: _t.Any) -> None:
        with self.thread_lock:
            self.set(f'settings.{name}', value)

    def get_service(self, name: str) -> _t.Any:
        service_id = '/'.join(('service', name))
        service = self.get(service_id)

        if service is missing:
            raise errors.UnknownService(service_id)

        cache_id = '/'.join(('service', name, 'cache'))
        cache = self.get(cache_id)

        # no cache
        if cache is missing:
            return service(self)
        else:
            # first call, cache it!
            if cache is required:
                self.set(cache_id, service(self))

            # nth call, use cached value
            return self.get(cache_id)

    def set_service(
        self,
        name: str,
        factory: _t.Callable[..., _t.Any],
        cache: bool = False
    ) -> None:
        with self.thread_lock:
            service_id = '/'.join(('service', name))
            self.set(service_id, factory)

            if cache:
                cache_id = '/'.join(('service', name, 'cache'))
                self.set(cache_id, required)
