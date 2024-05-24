.. _loader:

:tocdepth: 2

**loader** - application loader and constructor
-----------------------------------------------

It can be a tedious process to create an application from scratch, therefore there's
:py:class:`~kaiju_app.loader.ApplicationLoader` class which can create an app instance from a config dict.

The main method one want to use is :py:meth:`~kaiju_app.loader.ApplicationLoader.create_all`. It will import all service
dependencies, configure loggers and resolve the services loading order. See :ref:`configurator docs <configurator>`
on how to create config dicts from configuration files.

You can create a *service package* - a Python package which can be automatically imported by the application loader
on app init. To create a service package add `services.py` file to your Python package.

See the :ref:`packaging guide <guide_packages>` on how to create service packages compatible with the loader import system.

.. code-block:: yaml
  :caption: my_app/config.yaml

  packages:
    - my_package


.. code-block:: python

    from kaiju_app import ApplicationLoader, Application

    config = {...}
    loader = ApplicationLoader()
    app = loader.create_all(Application, config)

.. autoclass:: kaiju_app.loader.ApplicationLoader
   :members:

.. autoclass:: kaiju_app.loader.ProjectConfig
   :members:
   :exclude-members: __init__

.. autoclass:: kaiju_app.loader.AppConfig
   :members:
   :exclude-members: __init__

.. autoclass:: kaiju_app.loader.ServiceConfig
   :members:
   :exclude-members: __init__

.. autoclass:: kaiju_app.loader.ConfigurationError
   :show-inheritance:
   :exclude-members: __init__, __new__

.. autoclass:: kaiju_app.loader.DependencyCycleError
   :show-inheritance:
   :exclude-members: __init__, __new__

.. autoclass:: kaiju_app.loader.DependencyNotFound
   :show-inheritance:
   :exclude-members: __init__, __new__

.. autoclass:: kaiju_app.loader.ServiceNameConflict
   :show-inheritance:
   :exclude-members: __init__, __new__
