Libres
======

Libres is a reservations management library to reserve things like tables at
a restaurant or tickets at an event. It works with Python 3.9+
and requires Postgresql 9.2+.

`Documentation <http://libres.readthedocs.org/en/latest/>`_ | `Source <http://github.com/seantis/libres/>`_ | `Bugs <http://github.com/seantis/libres/issues>`_

**This library is at an experimental stage and not yet suitable for production**

.. image:: https://github.com/seantis/libres/actions/workflows/python-tox.yaml/badge.svg
  :target: https://github.com/seantis/libres/actions
  :alt:    Tests

.. image:: https://codecov.io/gh/seantis/libres/branch/master/graph/badge.svg?token=2WZfY5HwdE
  :target: https://codecov.io/gh/seantis/libres
  :alt:    Coverage

.. image:: https://img.shields.io/pypi/v/libres.svg
  :target: https://pypi.python.org/pypi/libres
  :alt:    Release

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

    pip install tox tox-uv
    tox

Limit the tests to a specific python version::

    tox -e py311

Conventions
-----------

Libres follows PEP8 as close as possible. To test for it run::

    tox -e ruff,flake8

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

Making a new Release
--------------------

Make sure all changes are in the HISTORY.rst, then bump the version::

    bump-my-version bump major|minor|patch
    git push && git push --tags

After this, create a new release on Github.
