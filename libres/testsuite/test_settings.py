from libres.testsuite import TestCase
from libres.conf import settings, default_settings


class TestSettings(TestCase):

    def tearDown(self):
        settings.reset()

    def test_set_settings(self):
        settings.dsn = 'custom'

        self.assertEqual(settings.dsn, 'custom')
        self.assertEqual(default_settings.dsn, None)

        settings.reset()
        self.assertEqual(settings.dsn, None)
        self.assertEqual(default_settings.dsn, None)
