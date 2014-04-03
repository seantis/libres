from uuid import UUID


def set_default_settings(registry):

    registry.set(
        'settings.dsn', None
    )
    registry.set(
        'settings.uuid_namespace', UUID('90fd2391-6707-4dc7-b2dd-8627f85e2c61')
    )
