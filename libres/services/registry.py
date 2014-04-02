import threading

from contextlib import contextmanager
from libres import errors


missing = object()


class Registry(object):

    def __init__(self, master_context='master'):
        self.lock = threading.RLock()

        with self.lock:
            self.contexts = {}
            self.locked = set()
            self.local = threading.local()
            self.single_instance_services = set()

            self.register_context(master_context)
            self.master_context = master_context
            self.local.current_context = master_context

    def is_existing_context(self, name):
        return name in self.contexts

    def is_current_context(self, name):
        return self.local.current_context == name

    def lock_context(self, name):
        with self.lock:
            self.locked.add(name)

    def unlock_context(self, name):
        with self.lock:
            self.locked.discard(name)

    def assert_context(self, name, must_exist):
        if must_exist:
            if not self.is_existing_context(name):
                raise errors.UnknownContext
        else:
            if self.is_existing_context(name):
                raise errors.ContextAlreadyExists

    def register_context(self, name):
        with self.lock:
            self.assert_context(name, must_exist=False)
            self.contexts[name] = {}

    def switch_context(self, name):
        self.assert_context(name, must_exist=True)
        self.local.current_context = name

    @contextmanager
    def context(self, name):
        previous = self.local.current_context
        self.switch_context(name)
        yield
        self.switch_context(previous)

    def get_current_context(self):
        return self.get_context(self.local.current_context)

    def get_context(self, name):
        self.assert_context(name, must_exist=True)
        return self.contexts[name]

    def get(self, key):
        context = self.get_current_context()
        master = self.contexts[self.master_context]

        if key in context:
            return context[key]
        elif key in master:
            return master[key]
        else:
            return missing

    def set(self, key, value):
        with self.lock:
            if self.local.current_context in self.locked:
                raise errors.ContextIsLocked

            self.get_current_context()[key] = value

    def get_service(self, name):
        service_id = '/'.join(('service', name))
        service = self.get(service_id)

        if service is missing:
            raise errors.UnknownService

        if service_id in self.single_instance_services:
            return service
        else:
            return service()

    def set_service(self, name, factory, single_instance=False):
        service_id = '/'.join(('service', name))

        with self.lock:
            if single_instance:
                self.single_instance_services.add(service_id)
                self.set(service_id, factory())
            else:
                self.single_instance_services.discard(service_id)
                self.set(service_id, factory)
