import threading
import reg

from contextlib import contextmanager


class Registry(object):

    # each context has a key and can only exist once
    existing_contexts = {}

    # the current context is local per thread and store in the configuration
    configuration = threading.local()

    # changing existing contexts must be made thread-safe manually
    lock = threading.Lock()

    def __init__(self, master_context):
        self.new_context(master_context)
        self.master_context = master_context

    def new_context(self, name):
        """ Creates a new context with the given name. Services not registered
        with the new_context are acquired through the master context.

        """
        with self.lock:
            assert name not in self.existing_contexts, """
                context already registered
            """

            self.existing_contexts[name] = reg.ClassRegistry()
            self.existing_contexts

    def switch_context(self, name):
        self.configuration.current_context = name

    @contextmanager
    def context(self, name):
        previous = getattr(self.configuration, 'current_context', None)
        self.switch_context(name)
        yield
        self.switch_context(previous)

    def get_current_context(self):
        name = getattr(self.configuration, 'current_context', None)
        return self.existing_contexts.get(name)

    def register_service(self, service, service_class, context=None):
        context = self.existing_contexts.get(
            context, self.get_current_context()
        )
        context.register(service, [], service_class)

    def get_service(self, service, context=None):
        context = self.existing_contexts.get(
            context, self.get_current_context()
        )
        factory = context.get(service, [])

        if factory is None:
            context = self.existing_contexts[self.master_context]
            factory = context.get(service, [])

        assert factory, """
            unknown service
        """

        return context.get(service, [])()
