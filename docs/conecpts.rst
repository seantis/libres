Conecpts
========

To really get an understanding of this libarary you should learn about a number
of core conecpts and design decisions we made whilst developing it.

Resources
---------

A resource is something that can be reserved. Say a table or a meeting room or
a ticket. For libres, resources are just keys with which to group things
together. They get their meaning from you, the Libres user.

Allocations
-----------

Your typical calendar on Google, Outlook or iCal presents you with a large
plane of free time. Clicking somewhere free you are able to enter an event
which then occupies a spot in your calendar.

In Libres you have to explicitly define what spots an event can occupy. Such
a definition is called an Allocation.

Allocations allocate time which may or may not be reserved. It is like a
restaurant saying "tonight we are open from six til twelve, which means our
tables are all available for reservation during that time".

If you really want to copy Google Calendar you could of course just allocate
everything on the go, but you would still be explicit about it.

Allocations may not overlap inside a single resource. Each period of time
within a resource is controlled by a single allocation because an allocation
essentially defines how time may be used. Having overlapping allocations would
result in conflicts.
