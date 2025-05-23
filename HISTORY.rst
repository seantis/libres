Changelog
---------

0.9.0 (23.05.2025)
~~~~~~~~~~~~~~~~~~~

- Replaces `JSON` database type with `JSONB`, this means
  Postgres as a backend is not required. You will also need
  to write a migration for existing JSON columns. You may use
  the following recipe using an alembic `Operations` object::

    operations.alter_column(
      'table_name',
      'column_name',
      type_=JSON,
      postgresql_using='"column_name"::jsonb'
    )

0.8.0 (15.01.2025)
~~~~~~~~~~~~~~~~~~~

- Adds support for Python 3.13
  [Daverball]

- Drops support for Python 3.8
  [Daverball]

- Modernizes type hints
  [Daverball]

0.7.3 (2024-08-21)
~~~~~~~~~~~~~~~~~~~

- Adds support for Python 3.12.
  [Daverball]

0.7.2 (2024-02-07)
~~~~~~~~~~~~~~~~~~~

- Fixes another incorrect type annotation in `Scheduler`.
  [Daverball]

0.7.1 (2024-01-18)
~~~~~~~~~~~~~~~~~~~

- Fixes some incorrect type annotations in `Scheduler`.
  [Daverball]

0.7.0 (2023-07-11)
~~~~~~~~~~~~~~~~~~~

- Drops support for Python 3.7 and adds support for 3.11
  [Daverball]

- Switches to ``pyproject.toml``
  [Daverball]

- Adds type annotations
  [Daverball]

- Changes ``Scheduler.allocate`` to avoid hundreds of separate
  SQL queries when passing in hundreds of datetime ranges in
  order to identify existing overlapping allocations.

  Performance could still be a concern, since the query contains
  a lot of datetime comparisons. It might be quicker in the common case to filter to the minimum and maximum dates that
  have been passed in and doing the overlap checks entirely in
  Python. We will need to keep an eye on this.
  [Daverball]

0.6.1 (2023-03-29)
~~~~~~~~~~~~~~~~~~~

- Adds additional parameters to ``Scheduler.remove_unused allocations``
  to filter the to be removed Allocations by weekday or
  whether or not they belong to a group.
  [Daverball]

- Fixes bug in ``Scheduler.search_allocations``. It did not
  align the days parameter properly to the timezone of the
  Allocation/Scheduler.
  [Daverball]

- Pins SQLAlchemy to versions before 2.0
  [Daverball]

0.6.0 (2022-08-10)
~~~~~~~~~~~~~~~~~~~

- Drops Python 3.6 support.
  [Daverball]

- Normalizes availability partitions on 23/25 hours to a 24 hour day
  so that DST transition days can be rendered the same as regular days.

  This can optionally be avoided by passing ``normalize_dst=False`` to
  the function.
  [Daverball]

- Adds ``Allocation.normalized_availability`` that reports the
  availability in the same normalized way.
  [Daverball]

- Adds extra parameters to ``Allocation.limit_timespan`` that match
  the new parameters added to ``sedate.get_date_range``.
  [Daverball]

0.5.4 (2022-06-15)
~~~~~~~~~~~~~~~~~~~

- Switches from Travis to GitHub Workflows.
  [msom]

- Resolves SQLAlchemy 1.4 warnings.
  [msom]

0.5.3 (2021-01-18)
~~~~~~~~~~~~~~~~~~~

- Fix collections deprecation warnings and fix tests.
  [dadadamotha]

0.5.2 (2019-11-11)
~~~~~~~~~~~~~~~~~~~

- Adds Python 3.8 compatibility.
  [href]

- Changes PostgreSQL version check to be distribution-independent.
  [href]

0.5.1 (2019-01-23)
~~~~~~~~~~~~~~~~~~~

- Fixes overlapping allocations not being skipped in all cases.
  [href]

0.5.0 (2019-01-17)
~~~~~~~~~~~~~~~~~~~

- Adds the ability to skip overlapping allocations.
  [href]

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
