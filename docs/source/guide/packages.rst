.. _guide_packages:

Create service packages
-----------------------

You can create a *service package* - a Python package which can be imported by the application loader
on app init. To create a service package add `services.py` file to your Python package.

.. code-block::

  | /
  | ├── my_package/
  | │   ├── services.py
  | │   ├── ...
  | │   └── __init__.py

In `services.py` you must import all your service classes what should be imported.

.. code-block:: python
  :caption: my_package/services.py

  from my_package.service_1 import MyService1
  from my_package.service_2 import MyService2

You can now use put your package name in the configuration file in the `packages` section. See the
:ref:`configuration specification <config-spec>` for detail. Note that you still need to install the package with `pip`
before launching the app.

Your services will be registered under `<package name>.<class name>`.

.. code-block:: yaml
  :caption: my_app/settings/config.yml

  app:
    ...
    services:
      - cls: my_package.MyService1
      - cls: my_package.MyService2
