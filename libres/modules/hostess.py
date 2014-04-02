from libres import registry
from libres.modules.database import Database
from libres.modules.utils import context_specific


class Hostess(object):

    def __init__(self, context):
        self.context = context

        if not registry.is_existing_context(self.context):
            registry.register_context(self.context)

        self.db = Database(self.context)

    @context_specific
    def get_config(self, name):
        return registry.get(name)

    @context_specific
    def set_config(self, name, value):
        registry.set(name, value)
