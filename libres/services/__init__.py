def setup_registry():

    from libres.services.registry import Registry
    from libres.services.email import EmailService
    from libres.services.db.session import SessionProvider
    from libres.services.settings import set_default_settings

    registry = Registry()

    with registry.context(registry.master_context):
        registry.set_service('email', EmailService)
        registry.set_service('session', SessionProvider, single_instance=True)

        set_default_settings(registry)

    registry.lock_context(registry.master_context)

    return registry
