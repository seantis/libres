import os.path
import unittest

from uuid import uuid4
from textwrap import dedent


class TestCase(unittest.TestCase):

    @property
    def dsn(self):
        if not hasattr(self, '_dsn'):
            self._dsn = self.get_local_dsn()

        return self._dsn

    def get_local_dsn(self):
        import libres

        src_folder = '/'.join((libres.__file__).split('/')[:-2])
        dsn_file = os.path.join(src_folder, 'test.dsn')

        if os.path.exists(dsn_file):
            return open(dsn_file).read().strip('\n').strip('')
        else:
            assert False, dedent("""
                Cannot run tests because the postgres database is not
                configured. Add a test.dsn file to the root of the libres
                repository and put a dsn to your local postgresql database
                into it. Be sure to use a test database that is not used
                otherwise, als all existing records will be deleted.
            """)

    def get_random_string(self):
        return uuid4().hex
