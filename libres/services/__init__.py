def setup_registry():

    from libres.services.registry import Registry
    from libres.services.email import EmailService
    from libres.services.db.session import SessionProvider
    from libres.services.settings import set_default_settings

    registry = Registry()

    def session_factory():
        return SessionProvider(registry.get('settings.dsn'))

    def email_factory():
        return EmailService()

    with registry.context(registry.master_context):
        registry.set_service('email', email_factory)
        registry.set_service('session', session_factory)

        set_default_settings(registry)

    registry.lock_context(registry.master_context)

    return registry
