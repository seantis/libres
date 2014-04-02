import functools
from libres import registry


def context_specific(fn):

    @functools.wraps(fn)
    def wrapped(self, *args, **kwargs):
        with registry.context(self.context):
            return fn(self, *args, **kwargs)

    return wrapped
