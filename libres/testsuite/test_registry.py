import threading
import random

from libres.testsuite import TestCase
from libres.modules import errors
from libres.services.registry import Registry


class TestRegistry(TestCase):

    def test_registry_contexts(self):
        r = Registry()

        self.assertEqual(r.master_context, 'master')
        self.assertEqual(r.local.current_context, 'master')

        self.assertTrue(r.is_existing_context('master'))
        self.assertFalse(r.is_existing_context('foo'))

        r.register_context('foo')
        self.assertTrue(r.is_existing_context('foo'))
        self.assertEqual(r.local.current_context, 'master')

        r.switch_context('foo')
        self.assertEqual(r.local.current_context, 'foo')

        with r.context('master'):
            self.assertEqual(r.local.current_context, 'master')

        self.assertEqual(r.local.current_context, 'foo')
        self.assertEqual(r.get_context('foo'), r.get_current_context())

    def test_locked_contexts(self):
        r = Registry()
        r.set('foo', 'bar')

        r.lock_context('master')
        self.assertRaises(errors.ContextIsLocked, r.set, 'foo', 'bar')

    def test_master_fallback(self):
        r = Registry()
        r.set('settings.host', 'localhost')
        self.assertEqual(r.get('settings.host'), 'localhost')

        r.register_context('my-app')
        self.assertEqual(r.get('settings.host'), 'localhost')

        r.switch_context('my-app')
        self.assertEqual(r.get('settings.host'), 'localhost')

        r.set('settings.host', 'remotehost')
        self.assertEqual(r.get('settings.host'), 'remotehost')

        r.switch_context('master')
        self.assertEqual(r.get('settings.host'), 'localhost')

    def test_services(self):
        r = Registry()

        r.set_service('service', factory=object, single_instance=False)
        first_call = r.get_service('service')
        second_call = r.get_service('service')

        self.assertFalse(first_call is second_call)

        r.set_service('service', factory=object, single_instance=True)
        first_call = r.get_service('service')
        second_call = r.get_service('service')

        self.assertTrue(first_call is second_call)

    def test_threading_contexts(self):
        r = Registry()

        class Application(threading.Thread):

            def __init__(self, context, registry):
                threading.Thread.__init__(self)
                self.registry = registry
                self.context = context

            def run(self):
                if not self.registry.is_existing_context(self.context):
                    self.registry.register_context(self.context)

                self.registry.switch_context(self.context)
                self.registry.set('current_context', self.context)
                self.result = self.registry.get_current_context()

            def join(self):
                result = self.result
                threading.Thread.join(self)
                return result

        for i in range(0, 100):

            threads = [
                Application('one', r),
                Application('two', r),
                Application('three', r),
                Application('four', r)
            ]

            random.shuffle(threads)

            for t in threads:
                t.start()

            results = [t.join()['current_context'] for t in threads]
            self.assertEqual(
                sorted(results),
                sorted(['one', 'two', 'three', 'four'])
            )
