Changelog
---------

0.1.0 (2015-7-30)
~~~~~~~~~~~~~~~~~

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