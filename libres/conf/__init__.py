from . import default_settings


class UserSettings(object):
    pass


class Settings(object):

    _user_settings = UserSettings()

    def reset(self):
        self._user_settings.__dict__ = {}

    def __getattr__(self, name):
        if hasattr(self._user_settings, name):
            return getattr(self._user_settings, name)
        elif hasattr(default_settings, name):
            return getattr(default_settings, name)
        else:
            raise AttributeError

    def __setattr__(self, name, value):
        setattr(self._user_settings, name, value)

    def __dir__(self):
        return list(self._user_settings.__dict__) + dir(default_settings)


settings = Settings()
