from libres.testsuite import TestCase
from libres import new_hostess


class TestHostess(TestCase):

    def test_context(self):
        # the first argument of a new hostess is the context
        hostess = new_hostess('KFC', 'New York Time Square')
        hostess.set_config('settings.dsn', 'localhost')

        # hostesses with the same context share the same settings
        self.assertEqual(hostess.get_config('settings.dsn'), 'localhost')

        hostess = new_hostess('KFC', 'Kuala Lumpur KLCC')
        self.assertEqual(hostess.get_config('settings.dsn'), 'localhost')

        # hostesses with different contexts do not share it
        hostess = new_hostess('Burger King', 'Lucerne')
        self.assertEqual(hostess.get_config('settings.dsn'), None)
