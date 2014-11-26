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

    def get_service(self, name):
        with registry.context(self.context):
            return registry.get_service(name)

    def set_service(self, name, value):
        with registry.context(self.context):
            return registry.set_service(name, value)

    @property
    def session_provider(self):
        return self.get_service('session_provider')

    @property
    def session(self):
        return self.session_provider.session()

    @property
    def serial_session(self):
        return self.session_provider.sessionstore.serial

    @property
    def readonly_session(self):
        return self.session_provider.sessionstore.readonly

    def validate_email(self, email):
        return self.get_service('email_validator')(email)

    def is_allocation_exposed(self, allocation):
        exposure = self.get_service('exposure')
        return exposure.is_allocation_exposed(allocation)
