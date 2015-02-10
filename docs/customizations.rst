Customizations
==============

.. _custom-json:

Custom JSON Serializer/Deserializer
-----------------------------------

If you want to provide your own json serializer/deserializer, you
can do that on the context::

    import libres.context

    def session_provider(context):
        return libres.context.session.SessionProvider(
            context.get_setting('dsn'),
            engine_config={
                'json_serializer': my_json_dumps,
                'json_deserializer': my_json_loads
            }
    )

    context = libres.registry.register_context('flask-exmaple')
    context.set_setting('dsn', postgresql.url())
    context.set_service('session_provider', session_provider)
