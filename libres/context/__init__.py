def setup_registry():

    import json
    import re

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.context.settings import set_default_settings
    from libres.context.exposure import Exposure

    registry = Registry()

    def session_provider():
        return SessionProvider(registry.get('settings.dsn'))

    def email_validator_factory():
        # A very simple and stupid email validator. It's way too simple, but
        # it can be extended to do more powerful checks.
        def is_valid_email(email):
            return re.match(r'[^@]+@[^@]+\.[^@]+', email)

        return is_valid_email

    def exposure_factory():
        return Exposure()

    with registry.context(registry.master_context):
        registry.set_service('email_validator', email_validator_factory)
        registry.set_service('session_provider', session_provider, cache=True)
        registry.set_service('exposure', exposure_factory)
        registry.set_service('json_dumps', lambda: json.dumps)
        registry.set_service('json_loads', lambda: json.loads)

        set_default_settings(registry)

    registry.lock_context(registry.master_context)

    return registry
