import threading
import pytest
import random

from libres.modules import errors
from libres.context.registry import Registry


def test_registry_contexts():
    r = Registry()

    assert r.master_context.name == 'master'
    assert r.master_context is r.current_context
    assert r.is_existing_context('master')
    assert not r.is_existing_context('foo')

    r.register_context('foo')

    assert r.is_existing_context('foo')
    assert r.current_context.name == 'master'

    r.switch_context('foo')
    assert r.local.current_context.name == 'foo'

    bar_context = r.register_context('bar')
    with bar_context.as_current_context():
        assert r.local.current_context is bar_context

    with r.context('master'):
        assert r.local.current_context.name == 'master'

    assert r.current_context.name == 'foo'
    assert r.get_context('foo') == r.get_current_context()

    bar_context.switch_to()
    assert r.current_context.name == 'bar'


def test_autocreate():
    r = Registry()

    ctx = r.get_context('yo', autocreate=True)

    assert r.get_context('yo', autocreate=True) is ctx
    assert r.get_context('yo') is ctx


def test_assert_existence():
    r = Registry()

    with pytest.raises(errors.UnknownContext):
        r.assert_exists('foo')

    r.register_context('foo')

    with pytest.raises(errors.ContextAlreadyExists):
        r.assert_does_not_exist('foo')


def test_replace():
    r = Registry()

    ctx = r.register_context('gabba gabba')
    ctx.set_setting('test', 'one')

    assert ctx.get_setting('test') == 'one'

    ctx = r.register_context('gabba gabba', replace=True)
    assert ctx.get_setting('test') != 'one'

    ctx.lock()

    with pytest.raises(errors.ContextIsLocked):
        ctx = r.register_context('gabba gabba', replace=True)


def test_different_registries():
    r1 = Registry()
    r2 = Registry()

    assert r1.master_context is not r2.master_context

    r1.register_context('foo')
    r2.register_context('foo')


def test_locked_contexts():
    r = Registry()

    context = r.register_context('test')
    context.set('foo', 'bar')
    context.lock()

    with pytest.raises(errors.ContextIsLocked):
        context.set('foo', 'bar')


def test_master_fallback():
    r = Registry()

    r.master_context.set_setting('host', 'localhost')
    assert r.master_context.get_setting('host') == 'localhost'

    my_app = r.register_context('my_app')
    assert my_app.get_setting('host') == 'localhost'

    my_app.switch_to()
    assert my_app.get_setting('host') == 'localhost'

    my_app.set_setting('host', 'remotehost')
    assert my_app.get_setting('host') == 'remotehost'

    another_app = r.register_context('another_app')
    another_app.switch_to()

    assert another_app.get_setting('host') == 'localhost'


def test_services():
    r = Registry()

    r.master_context.set_service('service', factory=lambda ctx: object())
    first_call = r.master_context.get_service('service')
    second_call = r.master_context.get_service('service')

    assert first_call is not second_call


def test_services_cache():
    r = Registry()

    r.master_context.set_service(
        'service', factory=lambda ctx: object(), cache=True
    )

    first_call = r.master_context.get_service('service')
    second_call = r.master_context.get_service('service')

    assert first_call is second_call


def test_threading_contexts():
    r = Registry()

    class Application(threading.Thread):

        def __init__(self, name, registry):
            threading.Thread.__init__(self)
            self.registry = registry
            self.name = name

        def run(self):
            if self.registry.is_existing_context(self.name):
                self.registry.get_context(self.name).switch_to()
            else:
                self.registry.register_context(self.name).switch_to()

            self.result = self.registry.get_current_context().name

        def join(self):
            threading.Thread.join(self)
            return self.result

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

        results = [t.join() for t in threads]
        assert sorted(results) == sorted(['one', 'two', 'three', 'four'])
