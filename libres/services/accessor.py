from libres import registry


class ContextAware(object):

    def __init__(self, context):
        self.context = context


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
        with registry.context(self.context):
            return registry.get_service('session').session()
