from datetime import datetime

from libres.tests import TestCase
from libres.db.models import ORMBase
from libres import new_scheduler


class TestScheduler(TestCase):

    def get_new_scheduler(self, context=None, name=None):
        return new_scheduler(
            context or self.get_random_string(),
            name or self.get_random_string(),
            settings={
                'settings.dsn': self.dsn
            }
        )

    def setUp(self):
        scheduler = self.get_new_scheduler()
        scheduler.setup_database()
        scheduler.commit()

    def tearDown(self):
        scheduler = self.get_new_scheduler()
        scheduler.context.readonly_session.close()

        ORMBase.metadata.drop_all(scheduler.context.serial_session.bind)
        scheduler.context.serial_session.close()

        scheduler.commit()

    def test_managed_allocations(self):
        start = datetime(2014, 4, 4, 14, 0)
        end = datetime(2014, 4, 4, 15, 0)
        timezone = 'Europe/Zurich'

        s1 = self.get_new_scheduler()

        allocations = s1.allocate((start, end), timezone)
        self.assertEqual(len(allocations), 1)

        s1.commit()

        s2 = self.get_new_scheduler()

        allocations = s2.allocate((start, end), timezone)
        self.assertEqual(len(allocations), 1)

        s2.commit()

        self.assertEqual(s1.managed_allocations().count(), 1)
        self.assertEqual(s2.managed_allocations().count(), 1)
