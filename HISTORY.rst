Changelog
---------

0.1.3 (unreleased)
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