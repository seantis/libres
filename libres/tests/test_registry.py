import threading
import pytest
import random

from libres.modules import errors
from libres.context.registry import Registry


def test_registry_contexts():
    r = Registry()

    assert r.master_context == 'master'
    assert r.current_context_name == 'master'

    assert r.is_existing_context('master')
    assert not r.is_existing_context('foo')

    r.register_context('foo')
    assert r.is_existing_context('foo')
    assert r.current_context_name == 'master'

    r.switch_context('foo')
    assert r.local.current_context == 'foo'

    with r.context('master'):
        assert r.local.current_context == 'master'

    assert r.current_context_name == 'foo'
    assert r.get_context('foo') == r.get_current_context()


def test_locked_contexts():
    r = Registry()
    r.set('foo', 'bar')

    r.lock_context('master')

    with pytest.raises(errors.ContextIsLocked):
        r.set('foo', 'bar')


def test_master_fallback():
    r = Registry()
    r.set('settings.host', 'localhost')
    assert r.get('settings.host') == 'localhost'

    r.register_context('my-app')
    assert r.get('settings.host') == 'localhost'

    r.switch_context('my-app')
    assert r.get('settings.host') == 'localhost'

    r.set('settings.host', 'remotehost')
    assert r.get('settings.host') == 'remotehost'

    r.switch_context('master')
    assert r.get('settings.host') == 'localhost'


def test_services():
    r = Registry()

    r.set_service('service', factory=object)
    first_call = r.get_service('service')
    second_call = r.get_service('service')

    assert first_call is not second_call


def test_services_cache():
    r = Registry()
    r.set_service('service', factory=object, cache=True)

    first_call = r.get_service('service')
    second_call = r.get_service('service')

    assert first_call is second_call


def test_threading_contexts():
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
            threading.Thread.join(self)
            result = self.result
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
        assert sorted(results) == sorted(['one', 'two', 'three', 'four'])
