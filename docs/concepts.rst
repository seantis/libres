Concepts
========

To really get an understanding of this libarary you should learn about a number
of core concepts and design decisions we made whilst developing it.

Resources
---------

A resource is something that can be reserved. Say a table or a meeting room or
a ticket. For libres, resources are just keys with which to group things
together. They get their meaning from you, the Libres consumer.

Allocations
-----------

Your typical calendar on Google, Outlook or iCal presents you with a large
plane of free time. Clicking somewhere free you are able to enter an event
which then occupies a spot in your calendar.

In Libres you have to explicitly define what spots an event can occupy. Such
a definition is called an *allocation*.

Allocations *allocate* time which may be reserved. It is like a restaurant
saying "tonight we are open from six til twelve, which means our tables are all
available for reservation during that time". This restaurant is allocating
the time from six until twelve in Libres-speak.

If you really want to copy Google Calendar you could of course just allocate
everything on the go, but you would still be explicit about it.

Allocations may not overlap inside a single resource. Each period of time
within a resource is controlled by a single allocation because an allocation
essentially defines how time may be used.

So depending on how a restaurant reservation system would be implemented, it
might make sense to have a separate resource for each table.

Reserved Slots
--------------

Allocations come in many forms, depending on your use case. In a meeting room
reservation you might have minutes available for reservation, though less
than 5 minutes is hardly something you would want to reserve ("I'm going
to need this meeting room for 90 seconds this afternoon, mmmkay?").

In a daycare center you might have days available for reservation, a kid either
comes for one day, maybe half a day, but not just for one hour.

To accomodate these different kind of allocations, Libres uses *reserved
slots*.

Reserved slots are the database records that make absolutely sure that no
reservation conflicts with another reservation. They accomplish that by
using the allocation together with the start time of the reservation as a
primary key on the database.

Reserved slots are unique inside an allocation, making sure that when two
reservations are made at the same time, only one will succeed.

Reservations
------------

Reserved slots always belong to someone. This someone is a "reservation". A
reserved slot always belongs to a reservation, but a reservation does not
necessarily point to a reserved slot.

This is because reservations may be in a waiting list, or they may be
attached to a session (meaning they are inside a reservation 'shopping cart').

Reservations need to be confirmed, before the reserved slots are created and
the reservation is linked to these reserved slots.

This confirmation isn't necessarily done by humans, but Libres expects you to
create a reservation and to confirm it in two distinct steps. You are free
to run these two steps at the same time, but you do have to run both of them.

Context / Registry
------------------

Libres operates on a context defined in a registry. The registry is global by
default (though you don't *have* to use global state).

The context holds a set of settings and services that are required by Libres,
but which can be overritten by you. It also acts as a namespace for your
application, making sure that multiple consumers of Libres may coexist in the
same process.

Usually you only want one context for your application and you don't ever want
to rename that context! This is because Libres binds resources, allocations,
reserved slots and reservations to the name of your context and any change to
that name will probably result in you losing 'sight' of your data (they will
still be there, but you won't find them under your new name).
