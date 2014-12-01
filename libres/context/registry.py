import threading

from contextlib import contextmanager

from libres.modules import errors
from libres.context.context import Context


class Registry(object):
    """ Holds a number of contexts, managing their creation and defining
    the currently active context.

    A global registry instance is found in libres::

        from libres import registry

    Though if global state is something you need to avoid, you can create
    your own version of the registry::

        from libres.context import setup_registry
        registry = setup_registry()

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
