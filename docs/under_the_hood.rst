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
single user transactions. If two  transactions arrive at the very same time,
only one transaction is accepted, while the other is stopped.

`See the nice documentation on the topic in the postgres manual.
<http://www.postgresql.org/docs/current/static/transaction-iso.html>`_.

Since serialized transactions are slower than normal transactions, Libres only
employs them for write operations. Read operations are left in the default
transaction level.

As a user you don't really have to care about this, though you might encounter
one of these errors::

    psycopg2.extensions.TransactionRollbackError
    libres.modules.errors.DirtyReadOnlySession
    libres.modules.errors.ModifiedReadOnlySession

A `TransactionRollbackError` occurs if the transaction you sent was denied
because another serial transaction was let through instead.

A `DirtyReadOnlySession` error occurs if you wrote something to the database
without comitting it.

A `ModifiedReadOnlySession` error occurs if you tried to write something to
the database without using the serial transaction.

See :class:`~libres.context.session.SessionStore`,
:class:`~libres.context.session.SessionProvider`,
:class:`~libres.context.session.Serializable` and
:class:`~libres.context.session.serialized` for implementation details.
