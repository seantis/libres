from datetime import datetime

from libres.tests import PostgresTestCase


class TestScheduler(PostgresTestCase):

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
