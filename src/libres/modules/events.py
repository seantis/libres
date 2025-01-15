""" Events are called by the :class:`libres.db.scheduler.Scheduler` whenever
something interesting occurs.

The implementation is very simple:

To add an event::

    from libres.modules import events

    def on_allocations_added(context_name, allocations):
        pass

    events.on_allocations_added.append(on_allocations_added)

To remove the same event::

    events.on_allocations_added.remove(on_allocations_added)

Events are called in the order they were added.
"""
from __future__ import annotations


from typing import overload
from typing import Protocol
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collections.abc import Callable
    from collections.abc import Sequence
    from datetime import datetime
    from typing_extensions import ParamSpec
    from uuid import UUID

    from libres.context.core import Context
    from libres.db.models import Allocation, Reservation

    _P = ParamSpec('_P')


class Event(list['Callable[_P, object]']):
    """Event subscription. By http://stackoverflow.com/a/2022629

    A list of callable objects. Calling an instance of this will cause a
    call to each item in the list in ascending order by index.

    """
    # NOTE: This is only used for binding the correct `ParamSpec` for callback
    #       protocols, otherwise we have to define a pseudo-type, that doesn't
    #       look like an instance of `Event`...
    @overload
    def __init__(self, f: type[Callable[_P, object]]) -> None: ...
    @overload
    def __init__(self) -> None: ...

    def __init__(self, f: object = None) -> None:
        return

    def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None:
        for f in self:
            f(*args, **kwargs)


on_allocations_added: Event[Context, Sequence[Allocation]] = Event()
""" Called when an allocation is added, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when adding the
        allocations.

    :allocations:
        The list of :class:`libres.db.models.Allocation` allocations to be
        commited.

"""

on_reservations_made: Event[Context, Sequence[Reservation]] = Event()
""" Called when a reservation is made, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when adding the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations to be
        commited. This is a list because one reservation can result in
        multiple reservation records. All those records will have the
        same reservation token and the same reservee email address.

"""

on_reservations_confirmed: Event[Context, Sequence[Reservation], UUID]
on_reservations_confirmed = Event()
""" Called when a reservation bound to a browser session is confirmed, with
the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when confirming the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        confirmed.

    :session_id:
        The session id that is being confirmed.
"""

on_reservations_approved: Event[Context, Sequence[Reservation]] = Event()
""" Called when a reservation is approved, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when approving the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        approved.

"""

on_reservations_denied: Event[Context, Sequence[Reservation]] = Event()
""" Called when a reservation is denied, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when denying the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        denied.

"""

on_reservations_removed: Event[Context, Sequence[Reservation]] = Event()
""" Called when a reservation is removed, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when removing the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        removed.

"""


# NOTE: We need to use a callback protocol, just because
#       we provide old_time/new_time by name, we probably
#       should do it positionally instead, but that would
#       be a potentially breaking change...
class _OnReservationTimeChangedCallback(Protocol):
    def __call__(
        self,
        context: Context,
        reservation: Reservation,
        /,
        old_time: tuple[datetime, datetime],
        new_time: tuple[datetime, datetime]
    ) -> None: ...


on_reservation_time_changed = Event(_OnReservationTimeChangedCallback)
""" Called when a reservation's time changes , with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when changing the
        reservation time.

    :reservation:
        The :class:`libres.db.models.Reservation` reservation whose time is
        changing.

    :old_time:
        A tuple of datetimes containing the old start and the old end.

    :new_time:
        A tuple of datetimes containing the new start and the new end.

"""
