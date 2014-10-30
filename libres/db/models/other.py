models = None


class OtherModels(object):
    """ Mixin class which allows for all models to access the other model
    classes without causing circular imports. """

    @property
    def models(self):
        global models
        if not models:
            from libres.db import models as m_
            models = m_

        return models
