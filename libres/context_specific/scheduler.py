from libres.models import ORMBase
from libres.services.session import serialized
from libres.services.accessor import ContextAccessor


class Scheduler(object):

    def __init__(self, context_name):
        self.context_name = context_name
        self.context = ContextAccessor(context_name)
        self.sessions = {
            'readonly': None,
            'serial': None
        }

    @property
    def session(self):
        provider = self.context.session_provider
        session_id = provider.is_serial and 'serial' or 'readonly'

        if not self.sessions[session_id]:
            self.sessions[session_id] = self.context.session()

        return self.sessions[session_id]

    @property
    def transaction(self):
        assert self.sessions['serial'] is not None
        return self.sessions['serial'].transaction

    @serialized
    def setup_database(self):
        ORMBase.metadata.create_all(self.session.bind)
