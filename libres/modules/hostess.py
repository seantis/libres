from libres import registry


class Hostess(object):

    def __init__(self, context):
        if context not in registry.existing_contexts:
            registry.new_context(context)

        self.context = context

    def service(self, name):
        return registry.get_service('email', self.context)

    def send_email(self):
        self.service('email').send_email(
            'subject',
            'sender@example.org',
            ['recipient@example.org'],
            'body'
        )
