import libres
import threading

from cached_property import cached_property
from contextlib import contextmanager
from libres.modules import errors


missing = object()
required = object()


class StoppableService(object):
    """ Services inheriting from this class have their stop_service method
    called when the service is discarded.

    Note that this only happens when a service is replaced with a new one
    and not when libres is stopped (i.e. this is *not* a deconstructor).

    """

    def stop_service(self):
        pass


class ContextServicesMixin(object):
    """ Provides access methods to the context's services. Expects
    the class that uses the mixin to provide self.context.

    The results are cached for performance.

    """

    @cached_property
    def is_allocation_exposed(self):
        return self.context.get_service('exposure').is_allocation_exposed

    @cached_property
    def generate_uuid(self):
        return self.context.get_service('uuid_generator')

    @cached_property
    def validate_email(self):
        return self.context.get_service('email_validator')

    def clear_cache(self):
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
    def session_provider(self):
        return self.context.get_service('session_provider')

    @property
    def session(self):
        """ Returns the current session. """
        return self.session_provider.session()

    def close(self):
        """ Closes the current session. """
        self.session.close()

    @property
    def begin_nested(self):
        return self.session.begin_nested

    def commit(self):
        return self.session.commit()

    def rollback(self):
        return self.session.rollback()


class Context(object):
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

    def __init__(self, name, registry=None, parent=None, locked=False):
        self.name = name
        self.registry = registry or libres.registry
        self.values = {}
        self.parent = parent
        self.locked = False
        self.thread_lock = threading.RLock()

    def __repr__(self):
        return "<Libres Context(name='{}')>".format(self.name)

    @contextmanager
    def as_current_context(self):
        with self.registry.context(self.name):
            yield

    def switch_to(self):
        self.registry.switch_context(self.name)

    def lock(self):
        with self.thread_lock:
            self.locked = True

    def unlock(self):
        with self.thread_lock:
            self.locked = False

    def get(self, key):
        if key in self.values:
            return self.values[key]
        elif self.parent:
            return self.parent.get(key)
        else:
            return missing

    def set(self, key, value):
        if self.locked:
            raise errors.ContextIsLocked

        with self.thread_lock:

            # If a value already exists it could be a stoppable service.
            # Stoppable services are called before they are stop so they
            # can clean up after themselves without having to wait for the GC.
            if isinstance(self.values.get(key), StoppableService):
                self.values[key].stop_service()

            self.values[key] = value

    def get_setting(self, name):
        return self.get('settings.{}'.format(name))

    def set_setting(self, name, value):
        with self.thread_lock:
            self.set('settings.{}'.format(name), value)

    def get_service(self, name):
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

    def set_service(self, name, factory, cache=False):
        with self.thread_lock:
            service_id = '/'.join(('service', name))
            self.set(service_id, factory)

            if cache:
                cache_id = '/'.join(('service', name, 'cache'))
                self.set(cache_id, required)
