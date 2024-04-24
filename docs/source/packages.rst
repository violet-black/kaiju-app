.. _packages-guide:

Create packages
===============

You can create a *service package* - a Python package which can be automatically imported by the application loader
on app init. To create a service package add `services.py` file to your Python package.

.. code-block::

  | /
  | ├── my_package/
  | │   ├── services.py
  | │   ├── ...
  | │   └── __init__.py

In `services.py` you must import all your services which need to be registered.

.. code-block:: python
  :caption: my_package/services.py

  from my_package import MyService1, MyService2

You can now use your package in the configuration file in the `packages` section. Here's an example of a configuration
yaml file. This would automatically register `MyService1` and `MyService2` classes in the application loader.

.. code-block:: yaml
  :caption: my_app/config.yaml

  packages:
    - my_package
