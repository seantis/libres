# -*- coding: utf-8 -*-
from setuptools import setup, Command


def get_long_description():
    for line in open('README.rst'):
        if '.. < package description' in line:
            break
        yield line


class PyTest(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import sys
        import subprocess
        errno = subprocess.call([sys.executable, 'runtests.py'])
        raise SystemExit(errno)

setup(
    name='libres',
    version='0.1',
    url='http://github.com/seantis/libres/',
    license='BSD',
    author='Denis Krienbühl',
    author_email='denis@href.ch',
    description='A library to reserve things',
    long_description='\n'.join(get_long_description()),
    packages=['libres'],
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'arrow',
        'dateutils',
        'psycopg2',
        'SQLAlchemy>=0.9',
    ],
    extras_require={
        'tests': [
            'pytest',
            'testing.postgresql',
            'tox'
        ],
        'example': [
            'flask',
            'isodate',
            'testing.postgresql'
        ]
    },
    cmdclass={'test': PyTest},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ],
    test_suite='libres.testsuite.suite'
)
