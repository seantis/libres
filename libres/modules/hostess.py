from libres import registry
from libres.modules.scheduler import Scheduler
from libres.services.accessor import ContextAccessor


class Hostess(object):

    def __init__(self, context_name, settings={}):
        if not registry.is_existing_context(context_name):
            registry.register_context(context_name)

        self.context_name = context_name
        self.context = ContextAccessor(context_name)

        for name, value in settings.items():
            self.context.set_config(name, value)

        self.scheduler = Scheduler(context_name)

    def setup(self):
        self.scheduler.setup_database()
        self.scheduler.transaction.commit()
