def setup_registry():
    from libres.services.registry import Registry
    from libres.services.email import EmailService
    from libres.services.settings import DefaultSettings

    registry = Registry('master')

    if not 'master' in registry.existing_contexts:
        registry.new_context('master')

    with registry.context('master'):
        registry.register_service('email', EmailService)
        registry.register_service('settings', DefaultSettings)

    return registry
