from libres import registry


class ContextAccessor(object):

    def __init__(self, context, autocreate):
        self.context = context

        if autocreate and not registry.is_existing_context(context):
            registry.register_context(context)

    @property
    def name(self):
        return self.context

    def get_setting(self, name):
        with registry.context(self.name):
            return registry.get('settings.{}'.format(name))

    def set_setting(self, name, value):
        with registry.context(self.name):
            return registry.set('settings.{}'.format(name), value)

    def get_service(self, name):
        with registry.context(self.name):
            return registry.get_service(name)

    def set_service(self, name, value):
        with registry.context(self.name):
            return registry.set_service(name, value)

    def validate_email(self, email):
        return self.get_service('email_validator')(email)

    def is_allocation_exposed(self, allocation):
        exposure = self.get_service('exposure')
        return exposure.is_allocation_exposed(allocation)
