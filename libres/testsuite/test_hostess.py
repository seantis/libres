from libres.testsuite import TestCase
from libres import new_hostess


class TestHostess(TestCase):

    def test_context(self):
        # the first argument of a new hostess is the context
        hostess = new_hostess('KFC')
        hostess.context.set_config('settings.dsn', 'localhost')

        # hostesses with the same context share the same settings
        self.assertEqual(
            hostess.context.get_config('settings.dsn'), 'localhost'
        )

        hostess = new_hostess('KFC')
        self.assertEqual(
            hostess.context.get_config('settings.dsn'), 'localhost'
        )

        # hostesses with different contexts do not share it
        hostess = new_hostess('Burger King')
        self.assertEqual(hostess.context.get_config('settings.dsn'), None)
