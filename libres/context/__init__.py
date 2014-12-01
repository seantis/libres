def setup_registry():

    import json
    import re

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.context.settings import set_default_settings
    from libres.context.exposure import Exposure

    registry = Registry()

    def session_provider(context):
        return SessionProvider(context.get_setting('dsn'))

    def email_validator_factory(context):
        # A very simple and stupid email validator. It's way too simple, but
        # it can be extended to do more powerful checks.
        def is_valid_email(email):
            return re.match(r'[^@]+@[^@]+\.[^@]+', email)

        return is_valid_email

    def exposure_factory(context):
        return Exposure()

    master = registry.master_context
    master.set_service('email_validator', email_validator_factory)
    master.set_service('session_provider', session_provider, cache=True)
    master.set_service('exposure', exposure_factory)
    master.set_service('json_dumps', lambda ctx: json.dumps)
    master.set_service('json_loads', lambda ctx: json.loads)

    set_default_settings(master)

    master.lock()

    return registry
