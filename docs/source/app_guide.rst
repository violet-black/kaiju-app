.. _app-guide:

Create and run apps
===================

*Application* is a number of services grouped together for some purpose. An application manages service initialization
and shutdown, stores services in its router and provides a shared log context, loggers and namespace for its services.

Create an app
-------------

First you need a configuration dict which describes an app and all its services. See :ref:`config-guide`
which describes the configuration process in detail. For now we'll just focus on the code. Suppose you have some simple
config for your app already.

.. code-block:: python

    minimal_config = {
        'packages': [],
        'logging': {},
        'app': {
            'name': 'my_app',
            'env': 'dev',
            'loglevel': 'INFO',
            'services': [{
                'cls': 'MyUselessService',
                'settings': {
                    'value': 42
                }
            }]
        }
    }

You can now pass it to the :py:meth:`kaiju_app.Configurator.create_configuration` to normalize it.

.. code-block:: python

    from kaiju_app import Configurator

    config = Configurator().create_configuration([minimal_config], [])

Next you need an :py:class:`kaiju_app.loader.ApplicationLoader` to actually create an :py:class:`~kaiju_app.app.Application` object.

.. code-block:: python

    from kaiju_app import Configurator, AppLoader

    loader = ApplicationLoader()

What about services? Service classes must be registered in the loader before initializing an application
(see :ref:`service-guide` on how to actually create service classes).

.. code-block:: python

    loader.service_classes['MyUselessService'] = MyUselessService

You are now ready to create an application!

.. code-block:: python

    from kaiju_app import Configurator, AppLoader

    loader = ApplicationLoader()
    app = loader.create_all(config)

Here's your app which you can pass to the :py:func:`kaiju_app.run_app` function. This will run the application
indefinitely unless a termination signal or *ctrl+C* is received.

.. code-block:: python

    import uvloop  # not necessary but you can use any loop library you want here

    run_app(app, loop=uvloop.new_event_loop())

Alternatively you could just run the application in its own asynchronous context. This could be useful when running
some scripts where all application logic is inside service 'init / close' methods. On exit it will automatically
shutdown all the services.

.. code-block:: python

    async def main(app):
        async with app:
            await app.services['MyUselessService'].do_noting_for_an_hour()

    asyncio.run_task(main(app))

Inspection
----------

You can inspect application and all its services.

.. code-block:: python

    app_info = await app.inspect()
