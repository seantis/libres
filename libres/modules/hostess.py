from libres import registry


class Hostess(object):

    def __init__(self, context):
        if context not in registry.existing_contexts:
            registry.new_context(context)

        self.context = context

    def session(self):
        return registry.get_service('session', self.context)
