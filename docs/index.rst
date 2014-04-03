Libres, a library for reservations
==================================

A while back we created `seantis.reservation`_, a Plone module to reserve
different kinds of resources. Spots at a daycare center, tables at a
restaurant, tickets for a show.

`seantis.reservation`_ was developed for a number of private and governement 
entities. It is used successfully by hundreds of users daily.

We have been asked a number of times to implement the same system in other
environments outside of Plone, which is why we chose to move it's core
features out into a library, usable by any kind of Python project.

Because we didn't want to suffer the second system effect we kept a lot of
things, including tests, the way they were. As a consequence certain things
could be easier, but most of the code is battle tested and we hope it works
for you.

.. toctree::
   :maxdepth: 2

   api

License
=======
Libres is released under the `MIT license`_.

Copyright (c) 2014 `Seantis GmbH`_.


.. _`seantis.reservation`: https://github.com/seantis/seantis.reservation
.. _`MIT license`: http://opensource.org/licenses/MIT
.. _`Seantis GmbH`: https://www.seantis.ch