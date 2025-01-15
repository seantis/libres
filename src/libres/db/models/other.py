from __future__ import annotations


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Protocol

    import libres.db.models as _models

    class _Models(Protocol):
        Allocation: type[_models.Allocation]
        ReservedSlot: type[_models.ReservedSlot]
        Reservation: type[_models.Reservation]


models = None


class OtherModels:
    """ Mixin class which allows for all models to access the other model
    classes without causing circular imports. """

    @property
    def models(self) -> _Models:
        global models
        if not models:
            # FIXME: libres.db exports ORMBase, do we really
            #        want to makes this accesible?
            from libres.db import models as m_
            models = m_

        return models
