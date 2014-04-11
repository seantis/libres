
Introduction
============

Python library to reserve stuff in a calendar.

Not a replacement for Outlook or Google Calendar, but a system to manage
reservations in the following usecases:

* Manage meeting rooms in a company. Users reserve the rooms themselves 
  without an authority confirming/denying their reservations.

* Manage nursery spots. Parents apply for a spot in the nursery for their kid.
  Someone at the nursery goes through the applicants and decides who gets the
  spot. Parents may add an application to the waitinglist.

* Manage community facilities. Citizens see the availability of facilities 
  online and call the municipality to reserve a facility. The management is 
  done internally (maybe through an already existing software). A readonly
  calendar shows the state on the website.

History
=======

A while back we created `seantis.reservation`_, a Plone module to reserve
different kinds of resources like the ones mentioned above.

`seantis.reservation`_ was developed for a number of private and governement 
entities. It is used successfully by hundreds of users daily.

We have been asked a number of times to implement the same system in other
environments outside of Plone, which is why we chose to move it's core
features out into a library, usable by any kind of Python project.

Because we didn't want to suffer the second system effect we kept a lot of
things, including tests, the way they were. As a consequence the API could be
quite a bit easier. On the plus side this means that the code is battle tested.

Goals
=====

**This project is currently in an alpha stadium**. We don't have a plan for the
release just yet and we will be tweaking the API heavily.

In the long run we obviously want the API to grow out of its historic roots
and be come more usable for humans. But don't expect this to happen over night.

Content
=======

.. toctree::
   :maxdepth: 2
   
   conecpts
   api


License
=======
Libres is released under the `MIT license`_.

Copyright (c) 2014 `Seantis GmbH`_.

Credits
=======

The calendar icon in the logo was designed by `Mani Amini`_ from `The Noun Project`_.

.. _`seantis.reservation`: https://github.com/seantis/seantis.reservation
.. _`MIT license`: http://opensource.org/licenses/MIT
.. _`Seantis GmbH`: https://www.seantis.ch
.. _`Mani Amini`: http://thenounproject.com/man1/
.. _`The Noun Project`: http://thenounproject.com/