Changelog
---------

0.4.0 (2017-06-16)
~~~~~~~~~~~~~~~~~~~

- Adds the ability to define the allocation/reservation class used by the
  scheduler.

0.3.1 (2017-06-07)
~~~~~~~~~~~~~~~~~~~

- Approved reservations may have session ids again, this restores backwards
  compatibiility with seantis.reservation.
  [href]

0.3.0 (2017-06-07)
~~~~~~~~~~~~~~~~~~~

- Enables polymorphy on reservations and allocations.
  [href]

0.2.4 (2017-01-10)
~~~~~~~~~~~~~~~~~~~

- Fixes reservation length check not working on DST days.
  [href]

0.2.3 (2016-10-25)
~~~~~~~~~~~~~~~~~~~

- Small performance improvements when dealing with many allocations.
  [href]

0.2.2 (2016-07-08)
~~~~~~~~~~~~~~~~~~~

- Ensures that all models are hashable to avoid problems with certain
  SQLAlchemy extensions/plugins.
  [href]

0.2.1 (2016-04-27)
~~~~~~~~~~~~~~~~~~~

- Reservations added to the same session may not be duplicated anymore.
  [href]

- Errors raised during reservation now have a 'reservation' attribute.
  [href]

0.2.0 (2016-04-26)
~~~~~~~~~~~~~~~~~~~

- Adds the ability to have a single token shared across multiple reservations
  in a single session.
  [href]

0.1.4 (2015-11-25)
~~~~~~~~~~~~~~~~~~~

- Adds the ability to change unapproved reservations.
  [href]

- Adds an extra check for start/end time. If the requested start/end time lies
  outside any possible allocation, an error is raised.
  [href]

- Ensures that approved reservations cannot be somehow removed during cleanup.
  [href]

0.1.3 (2015-09-03)
~~~~~~~~~~~~~~~~~~

- Adds a method to remove unused allocations.
  [href]

0.1.2 (2015-08-25)
~~~~~~~~~~~~~~~~~~

- Replaces libres.modules.calendar with sedate.
  [href]

- Naive start/end dates on the allocation are now automatically converted into
  the correct timezone when they are set.
  [href]

0.1.1 (2015-08-19)
~~~~~~~~~~~~~~~~~~

- It was possible to add or move an allocation to an invalid state (end before
  start date). This is now caught correctly.
  [href]

0.1.0 (2015-07-30)
~~~~~~~~~~~~~~~~~~

- BREAKING CHANGE: This release switches to a single SERIALIZED connections.
  
  Previously it used a READ COMMITED and a SERIALIZED connection in parallel,
  switching to the READ COMMITED connection for readonly queries and using
  the SERIALIZED connection for write queries.

  Using a serialized connection for everything reduces speed slightly (though
  we haven't been able to measure the effect on our lowish traffic sites). But
  it makes it easier to use libres with an existing connection when integrating
  it.

  It also simplifies the code by quite a bit.

0.0.2 (2015-03-16)
~~~~~~~~~~~~~~~~~~

- Fix being unable to delete an allocation with a quota > 1. 
  See issue #8.
  [href]

- Replace read session write guard with a simpler version.
  [href]

0.0.1 (2015-02-09)
~~~~~~~~~~~~~~~~~~

- Initial release.
  [href]