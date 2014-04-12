import unittest
from uuid import uuid4

from libres import new_scheduler
from libres.modules.postgresql import Postgresql

from libres.db.models import ORMBase


class TestCase(unittest.TestCase):
    pass


class PostgresTestCase(TestCase):

    created_schedulers = []

    def get_new_scheduler(self, context=None, name=None):
        scheduler = new_scheduler(
            context or uuid4().hex,
            name or uuid4().hex,
            settings={
                'settings.dsn': self.dsn
            }
        )
        self.created_schedulers.append(scheduler)

        return scheduler

    @property
    def dsn(self):
        return self.postgresql.url()

    @classmethod
    def setUpClass(cls):
        cls.postgresql = Postgresql()

    @classmethod
    def tearDownClass(cls):
        for scheduler in cls.created_schedulers:
            scheduler.dispose()

        cls.postgresql.stop()

    def setUp(self):
        scheduler = self.get_new_scheduler()
        scheduler.setup_database()
        scheduler.commit()

    def tearDown(self):
        scheduler = self.get_new_scheduler()
        scheduler.context.readonly_session.close()

        ORMBase.metadata.drop_all(scheduler.context.serial_session.bind)
        scheduler.commit()

        scheduler.context.serial_session.close()
