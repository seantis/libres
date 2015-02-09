FAQ
===

Why is *Database X* not an option? / Why does Postgresql < 9.1 not work?
------------------------------------------------------------------------

seantis.reservation relies on a Postgresql feature introduced in 9.1
called "Serialized Transactions". Serialized transactions are
transactions that, run on multiuser systems, are guaranteed to behave
like they are run on a singleuser system.

In other words, serialized transactions make it much easier to ensure
that the data stays sane even when multiple write transactions are run
concurrently.

Other databases, like Oracle, also support this feature and it would be
possible to support those databases as well. Patches welcome.

Note that MySQL has serialized transactions with InnoDB, but the
documentation does not make any clear guarantees and there is a debate
going on:

http://stackoverflow.com/questions/6269471/does-mysql-innodb-implement-true-serializable-isolation

For more information see :ref:`serialized-transactions`.

Why did you choose SQL anyway? Why not *insert your favorite NoSQL DB here*?
----------------------------------------------------------------------------

-  If a reservation is granted to you, noone else must get the same
   grant. Primary keys and transactions are a natural fit to ensure
   that.

-  Our data model is heavily structured and needs to be validated
   against a schema.

-  All clients must have the same data at all time. Not just eventually.

-  Complicated queries must be easy to develop as reporting matters.