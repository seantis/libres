Under the Hood
==============

.. _serialized-transactions:

Serialized Transactions
-----------------------

Working with dateranges in Libres often entails making sure that ranges don't
overlap. This often means that multiple records have to be considered before
a daterange can be changed.

One way to do this is to lock the relevant records and tables. Thus stopping
concurrent transactions around the same daterange from leaving the
database in an invalid state.

Libres uses serialized transactions instead, a feature of *proper*
databases like Postgres. Serialized transactions always behave like they were
single user transactions. If two transactions arrive at the very same time,
only one transaction is accepted, while the other is stopped.

`See the nice documentation on the topic in the postgres manual.
<http://www.postgresql.org/docs/current/static/transaction-iso.html>`_.

Serialized transactions do not come for free of course. They are slower, need
more cpu and use more memory. There's also always a chance that one transaction
will conflict with another transaction. This can be a problem if many
concurrent connections are happening.

As a user you don't really have to care about conflicts, though you might
encounter one this error::

    psycopg2.extensions.TransactionRollbackError

A `TransactionRollbackError` occurs if the transaction you sent was denied
because another serial transaction was let through instead.

We haven't had the need to do this, but if you *really* needed to scale libres,
you could possibly have two processes running. One process that only uses
read only transactions, one process that uses serialization.
