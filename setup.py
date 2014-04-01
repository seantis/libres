"""
Libres
------

Libres is a reservations management library to reserve things like tables at
a restaurant or tickets at an event. It works with Python 2.7 and Python 3.3+
and requires Postgresql 9.1+.

Libres is easy
``````````````

.. code:: python

    from libres import hostess

    hostess.allocate('18:00 - 22:00', 'daily')
    hostess.reserve('18:00 - 19:00', '2014-02-14', 'jon@example.org')

    hostess.reservations('2014-02-14')

        18:00 - 19:00   jon@example.org

"""
from setuptools import setup

setup(
    name='libres',
    version='0.11-dev',
    url='http://github.com/seantis/libres/',
    license='BSD',
    author='Denis Krienbühl',
    author_email='denis@href.ch',
    description='A library to reserve things',
    long_description=__doc__,
    packages=['libres', 'libres.testsuite'],
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=[
        'SQLAlchemy>=0.8.5',
        'psycopg2'
    ],
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
