Libres
======

Libres is a reservations management library to reserve things like tables at
a restaurant or tickets at an event. It works with Python 2.7 and Python 3.3+
and requires Postgresql 9.1.

`Documentation <http://libres.readthedocs.org/en/latest/>`_ | `Source <http://github.com/seantis/libres/>`_ | `Bugs <http://github.com/seantis/libres/issues>`_

**This library is at an experimental stage and not yet suitable for production**

.. image:: https://travis-ci.org/seantis/libres.svg?branch=master
  :target: https://travis-ci.org/seantis/libres
  :alt:    travis build status

.. image:: https://coveralls.io/repos/seantis/libres/badge.png
  :target: https://coveralls.io/r/seantis/libres
  :alt:    coveralls.io coverage

.. image:: https://pypip.in/v/libres/badge.png
    :target: https://pypi.python.org/pypi/libres
    :alt: Latest PyPI release

.. < package description

Run the Example
---------------

Go to examples/flask and install the requirements::

    cd examples/flask
    pip install -r requirements.txt

Run the example::

    python run.py

Open http://localhost:5000 and click around.

Run the Tests
-------------

Install tox and run it::

    pip install tox
    tox

Limit the tests to a specific python version::

    tox -e py27

Conventions
-----------

Libres follows PEP8 as close as possible. To test for it run::

    tox -e pep8

Libres uses `Semantic Versioning <http://semver.org/>`_

Build the Docs
--------------

Go to docs and install the requirements::

    cd docs
    pip install -r requirements.txt

Build the docs::

    make html

Open the docs::

    open build/html/index.html
