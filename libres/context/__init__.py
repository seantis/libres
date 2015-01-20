def setup_registry():

    import json
    import re

    from libres.context.registry import Registry
    from libres.context.session import SessionProvider
    from libres.context.settings import set_default_settings
    from libres.context.exposure import Exposure

    from uuid import uuid5 as new_namespace_uuid

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

    def uuid_generator_factory(context):
        def uuid_generator(name):
            return new_namespace_uuid(
                context.get_setting('uuid_namespace'),
                '/'.join((context.name, name))
            )
        return uuid_generator

    master = registry.master_context
    master.set_service('email_validator', email_validator_factory)
    master.set_service('session_provider', session_provider, cache=True)
    master.set_service('exposure', exposure_factory)
    master.set_service('uuid_generator', uuid_generator_factory)
    master.set_service('json_dumps', lambda ctx: json.dumps)
    master.set_service('json_loads', lambda ctx: json.loads)

    set_default_settings(master)

    master.lock()

    return registry
