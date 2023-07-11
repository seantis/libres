import typing as _t
if _t.TYPE_CHECKING:
    import libres.db.models as _models

    class _Models(_t.Protocol):
        Allocation: _t.Type[_models.Allocation]
        ReservedSlot: _t.Type[_models.ReservedSlot]
        Reservation: _t.Type[_models.Reservation]


models = None


class OtherModels:
    """ Mixin class which allows for all models to access the other model
    classes without causing circular imports. """

    @property
    def models(self) -> '_Models':
        global models
        if not models:
            # FIXME: libres.db exports ORMBase, do we really
            #        want to makes this accesible?
            from libres.db import models as m_
            models = m_

        return models
