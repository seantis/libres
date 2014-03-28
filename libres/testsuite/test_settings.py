from libres.testsuite import TestCase
from libres.conf import settings, default_settings


class TestSettings(TestCase):

    def tearDown(self):
        settings.reset()

    def test_set_settings(self):
        settings.DATABASE = 'custom'

        self.assertEqual(settings.DATABASE, 'custom')
        self.assertEqual(default_settings.DATABASE, None)

        settings.reset()
        self.assertEqual(settings.DATABASE, None)
        self.assertEqual(default_settings.DATABASE, None)
