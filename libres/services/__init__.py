def setup_services():
    from libres import registry
    from libres.services.email import EmailService

    if not 'master' in registry.existing_contexts:
        registry.new_context('master')

    with registry.context('master'):
        registry.register_service('email', EmailService)
