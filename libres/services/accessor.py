from libres import registry


class ContextAware(object):

    def __init__(self, context, autocreate):
        self.context = context

        if autocreate and not registry.is_existing_context(context):
            registry.register_context(context)

    @property
    def name(self):
        return self.context


class ContextAccessor(ContextAware):

    def get_config(self, name):
        with registry.context(self.context):
            return registry.get(name)

    def set_config(self, name, value):
        with registry.context(self.context):
            return registry.set(name, value)

    @property
    def session_provider(self):
        with registry.context(self.context):
            return registry.get_service('session')

    @property
    def session(self):
        return self.session_provider.session()

    @property
    def serial_session(self):
        return self.session_provider.sessionstore.serial

    @property
    def readonly_session(self):
        return self.session_provider.sessionstore.readonly
