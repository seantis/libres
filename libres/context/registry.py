import threading

from contextlib import contextmanager

from libres.modules import errors
from libres.context.core import Context


def create_default_registry():
    """ Creates the default registry for libres. """

    import re

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.context.settings import set_default_settings
    from libres.context.exposure import Exposure

    from uuid import uuid5 as new_namespace_uuid

    registry = Registry()

    def session_provider(context):
        return SessionProvider(context.get_setting('dsn'))

    def email_validator_factory(context):
        # A very simple and stupid email validator. It's way too simple, but
        # it can be extended to do more powerful checks.
        def is_valid_email(email):
            return re.match(r'[^@]+@[^@]+\.[^@]+', email)

        return is_valid_email

    def exposure_factory(context):
        return Exposure()

    def uuid_generator_factory(context):
        def uuid_generator(name):
            return new_namespace_uuid(
                context.get_setting('uuid_namespace'),
                '/'.join((context.name, name))
            )
        return uuid_generator

    master = registry.master_context
    master.set_service('email_validator', email_validator_factory)
    master.set_service('session_provider', session_provider, cache=True)
    master.set_service('exposure', exposure_factory)
    master.set_service('uuid_generator', uuid_generator_factory)

    set_default_settings(master)

    master.lock()

    return registry


class Registry(object):
    """ Holds a number of contexts, managing their creation and defining
    the currently active context.

    A global registry instance is found in libres::

        from libres import registry

    Though if global state is something you need to avoid, you can create
    your own version of the registry::

        from libres.context.registry import create_default_registry
        registry = create_default_registry()

    """

    master_context = None

    def __init__(self):
        self.thread_lock = threading.RLock()

        with self.thread_lock:
            self.contexts = {}
            self.local = threading.local()

        self.master_context = self.register_context('master')

    @property
    def current_context(self):
        if not hasattr(self.local, 'current_context'):
            self.local.current_context = self.master_context

        return self.local.current_context

    def is_existing_context(self, name):
        return name in self.contexts

    def assert_not_locked(self, name):
        if self.get_context(name).locked:
            raise errors.ContextIsLocked

    def assert_exists(self, name):
        if not self.is_existing_context(name):
            raise errors.UnknownContext

    def assert_does_not_exist(self, name):
        if self.is_existing_context(name):
            raise errors.ContextAlreadyExists

    def register_context(self, name, replace=False):
        """ Registers a new context with the given name and returns it.

        """
        with self.thread_lock:
            if replace:
                if self.is_existing_context(name):
                    self.assert_not_locked(name)
            else:
                self.assert_does_not_exist(name)

            self.contexts[name] = Context(
                name,
                registry=self,
                parent=self.master_context,
                locked=False
            )

            return self.contexts[name]

    def switch_context(self, name):
        with self.thread_lock:
            self.assert_exists(name)
            self.local.current_context = self.get_context(name)

    @contextmanager
    def context(self, name):
        previous = self.current_context.name
        self.switch_context(name)
        yield self.current_context
        self.switch_context(previous)

    def get_current_context(self):
        return self.current_context

    def get_context(self, name, autocreate=False):
        if not autocreate:
            self.assert_exists(name)
        elif not self.is_existing_context(name):
            self.register_context(name)

        return self.contexts[name]
