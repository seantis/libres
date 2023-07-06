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


import typing as _t
if _t.TYPE_CHECKING:
    from datetime import datetime
    from typing_extensions import ParamSpec, TypeAlias
    from uuid import UUID

    from libres.context.core import Context
    from libres.db.models import Allocation, Reservation

    _P = ParamSpec('_P')
    _dtrange: TypeAlias = _t.Tuple[datetime, datetime]

    class Event(_t.List[_t.Callable[_P, _t.Any]]):
        def __call__(self, *args: _P.args, **kwargs: _P.kwargs) -> None: ...

    _OnReservationsConfirmed: TypeAlias = Event[
        Context, _t.Sequence[Reservation], UUID
    ]

    # FIXME: This is unnecessarily complex, because we call
    #        start_time and end_time on this callback by name
    #        rather than positionally.
    class _OnReservationTimeChangedCallback(_t.Protocol):
        def __call__(
            self,
            __context: Context,
            __reservation: Reservation,
            old_time: _dtrange,
            new_time: _dtrange
        ) -> None: ...

    class _OnReservationTimeChanged(
        _t.List[_OnReservationTimeChangedCallback]
    ):
        def __call__(
            self,
            __context: Context,
            __reservation: Reservation,
            old_time: _dtrange,
            new_time: _dtrange
        ) -> None: ...

else:
    class Event(list):
        """Event subscription. By http://stackoverflow.com/a/2022629

        A list of callable objects. Calling an instance of this will cause a
        call to each item in the list in ascending order by index.

        """
        def __call__(self, *args: _t.Any, **kwargs: _t.Any) -> None:
            for f in self:
                f(*args, **kwargs)


on_allocations_added: 'Event[Context, _t.Sequence[Allocation]]' = Event()
""" Called when an allocation is added, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when adding the
        allocations.

    :allocations:
        The list of :class:`libres.db.models.Allocation` allocations to be
        commited.

"""

on_reservations_made: 'Event[Context, _t.Sequence[Reservation]]' = Event()
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

on_reservations_confirmed: '_OnReservationsConfirmed' = Event()
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

on_reservations_approved: 'Event[Context, _t.Sequence[Reservation]]' = Event()
""" Called when a reservation is approved, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when approving the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        approved.

"""

on_reservations_denied: 'Event[Context, _t.Sequence[Reservation]]' = Event()
""" Called when a reservation is denied, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when denying the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        denied.

"""

on_reservations_removed: 'Event[Context, _t.Sequence[Reservation]]' = Event()
""" Called when a reservation is removed, with the following arguments:

    :context:
        The :class:`libres.context.core.Context` used when removing the
        reservation.

    :reservations:
        The list of :class:`libres.db.models.Reservation` reservations being
        removed.

"""

on_reservation_time_changed: '_OnReservationTimeChanged'
on_reservation_time_changed = Event()  # type:ignore[assignment]
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
