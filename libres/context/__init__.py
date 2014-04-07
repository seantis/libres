def setup_registry():

    import json
    import re

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.context.settings import set_default_settings
    from libres.context.exposure import Exposure

    registry = Registry()

    def session_factory():
        return SessionProvider(
            registry.get('settings.dsn'),
            engine_config={
                'json_serializer': registry.get_service('json_serializer'),
                'json_deserializer': registry.get_service('json_deserializer')
            }
        )

    def email_validator_factory():
        # A very simple and stupid email validator. It's way too simple, but
        # it can be extended to do more powerful checks.
        def is_valid_email(email):
            return re.match(r'[^@]+@[^@]+\.[^@]+', email)

        return is_valid_email

    def json_serializer_factory():
        return json.dumps

    def json_deserializer_factory():
        return json.loads

    def exposure_factory():
        return Exposure()

    with registry.context(registry.master_context):
        registry.set_service('email_validator', email_validator_factory)
        registry.set_service('session', session_factory)
        registry.set_service('json_serializer', json_serializer_factory)
        registry.set_service('json_deserializer', json_deserializer_factory)
        registry.set_service('exposure', exposure_factory)

        set_default_settings(registry)

    registry.lock_context(registry.master_context)

    return registry
