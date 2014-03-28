import libres


class Hostess(object):

    def __init__(self):
        self.context('master')

    def context(self, context):
        if context not in libres.registry.existing_contexts:
            libres.registry.new_context(context)

        self.ctx = context

    def send_email(self):
        service = libres.registry.get_service('email', self.ctx)
        service.send_email(
            'subject',
            'sender@example.org',
            ['recipient@example.org'],
            'body'
        )
