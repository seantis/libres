from libres import registry


class Hostess(object):

    def __init__(self, context, id):
        self.context = context
        self.id = id

        if not registry.is_existing_context(self.context):
            registry.register_context(self.context)

    @property
    def session(self):
        with registry.context(self.context):
            return registry.get_service('session').session()

    def get_config(self, name):
        with registry.context(self.context):
            return registry.get(name)

    def set_config(self, name, value):
        with registry.context(self.context):
            registry.set(name, value)
