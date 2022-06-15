# -*- coding: utf-8 -*-
from setuptools import setup


def get_long_description():

    for line in open('README.rst'):
        if '.. < package description' in line:
            break
        yield line

    for line in open('HISTORY.rst'):
        yield line


setup(
    name='libres',
    version='0.5.4',
    url='http://github.com/seantis/libres/',
    license='BSD',
    author='Denis Krienbühl',
    author_email='denis@href.ch',
    description='A library to reserve things',
    long_description=''.join(get_long_description()),
    packages=['libres'],
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'cached_property >= 1.2.0',
        'python-dateutil',
        'psycopg2-binary',
        'pytz',
        'sedate',
        'SQLAlchemy>=0.9',
    ],
    extras_require=dict(
        test=[
            'GitPython',
            'jsonpickle',
            'mock',
            'pytest',
            'pytest-codecov',
            'testing.postgresql',
        ],
    ),
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
