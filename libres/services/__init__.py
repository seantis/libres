def setup_registry():

    import json

    from libres.services.registry import Registry
    from libres.services.email import EmailService
    from libres.services.session import SessionProvider
    from libres.services.settings import set_default_settings

    registry = Registry()

    def session_factory():
        return SessionProvider(
            registry.get('settings.dsn'),
            engine_config={
                'json_serializer': registry.get_service('json_serializer'),
                'json_deserializer': registry.get_service('json_deserializer')
            }
        )

    def email_factory():
        return EmailService()

    def json_serializer_factory():
        return json.dumps

    def json_deserializer_factory():
        return json.loads

    with registry.context(registry.master_context):
        registry.set_service('email', email_factory)
        registry.set_service('session', session_factory)
        registry.set_service('json_serializer', json_serializer_factory)
        registry.set_service('json_deserializer', json_deserializer_factory)

        set_default_settings(registry)

    registry.lock_context(registry.master_context)

    return registry
