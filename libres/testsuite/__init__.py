import os
import sys
import unittest


class TestCase(unittest.TestCase):
    pass


def suite():
    setup_file = sys.modules['__main__'].__file__
    setup_dir = os.path.abspath(os.path.dirname(setup_file))

    return unittest.defaultTestLoader.discover(setup_dir)
