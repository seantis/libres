Libres
======

Libres is a reservations management library to reserve things like tables at
a restaurant or tickets at an event. It works with Python 2.7 and Python 3.3+
and requires Postgresql 9.2+.

.. < package description

**This package is under heavy development**

Run the Tests
-------------
    
Install tox and run it:

    pip install tox
    tox

Limit the tests to a specific python version:

    tox -e py27

Documentation
-------------

http://libres.readthedocs.org/

Build the Docs
--------------

Go to docs and install the requirements:

    cd docs
    pip install -r requirements.txt

Build the docs:

    make html

Open the docs:

    open build/html/index.html

Run the Example
---------------

Go to examples/flask and install the requirements:

    cd examples/flask
    pip install -r requirements.txt

Run the example:

    python run.py

Open http://localhost:5000 and click around.

Batches!
--------

.. image:: https://travis-ci.org/seantis/libres.svg?branch=master
  :target: https://travis-ci.org/seantis/libres
  :alt:    travis build status