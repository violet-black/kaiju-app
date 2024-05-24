.. _guide_service:

:tocdepth: 2

Guide to services
-----------------

What's a service? You can think of a :py:class:`~kaiju_app.app.Service` as of an encapsulated of an application logic,
similar to class in OOP. For example, a cache service may manage all the app interactions with an external cache storage;
or a payments service may manage transactions in an online store.

The difference between a service and just a class is that a service provides a common interface for initialization,
health checks and termination inside of an app and can also use app dependency resolve algorithm. This means that
a service is more independent compared to a normal class, i.e. you can reference a service by its class name in a
config file and the :py:class:`~kaiju_app.loader.ApplicationLoader` will do the rest including finding and linking
the service to all of its dependencies, initialization, configuration, etc.

This allows you to create highly *modular* applications where you can manage application components by installing
packages and editing config files without a need to edit the source code.

Create services
^^^^^^^^^^^^^^^

So how to create a :py:class:`~kaiju_app.app.Service`? You need to inherit from the service class and that's all.

Obviously, it's not a very useful example. Let's create something more practical. Suppose you need an external cache
(Keydb or Redis) for your services to store temporary data such as client sessions, product names and descriptions, etc.
At this moment you notice that such functionality needs a few crucial things.

1. Initialization: you need to create a connection pool to Redis and ensure it is working.
2. Shared functionality: multiple unconnected parts of your code may need to access and write cache.
3. Consistency: key names must match a certain pattern to prevent conflicts.

These are good reasons to write a new special service for this purpose. Therefore let's create a new *caching service*.

Start by inheriting from :py:class:`~kaiju_app.app.Service` class and creating an interface for the caching methods.

.. code-block:: python
  :caption: app/cache.py

    from dataclasses import dataclass
    from kaiju_app import Service

    @dataclass(kw_only=True)
    class RedisCache(Service):

        async def get(self, key: str) -> object | None: ...

        async def set(self, key: str, value: object) -> None: ...

You also would need to add you service to the map of service classes in your :py:class:`~kaiju_app.loader.ApplicationLoader`.

.. code-block:: python
  :caption: app/__init__.py

  from kaiju_app import ApplicationLoader
  from app.cache import RedisCache

  loader = ApplicationLoader()
  loader.service_classes['RedisCache'] = RedisCache

Now even before you implemented the actual logic you can use this service in your other services using
a dependency field — :py:func:`~kaiju_app.app.service`. This field will *automatically* tell the
:py:class:`~kaiju_app.loader.ApplicationLoader` that an instance of your *CacheService* must be inserted into
`ProductInfo.cache` attribute before the application start.

.. code-block:: python
  :caption: app/products.py

    from dataclasses import dataclass
    from kaiju_app import service, Service
    from app.cache import RedisCache

    @dataclass(kw_only=True)
    class ProductInfo(Service):

        cache: RedisCache = service()

        async def get_product(self, id: str) -> object | None:
            product = await self.cache.get(f'product.{id}')
            if product is not None:
                return product
            product = await self.products_table.select().where(id=id)
            return product

.. note::

  Keep in mind that :py:func:`~kaiju_app.app.service` is resolved
  by the :py:class:`~kaiju_app.loader.ApplicationLoader` and *not by the app itself*. If you create an app manually
  you also have to pass dependencies manually as arguments in service `__init__`.

  This may be useful when doing tests, because the services themselves don't check against `isinstance` for dependencies,
  thus you can safely provide a mock object there.

Now you can create an implementation for your cache. Obviously you need to initialize a connection pool and test
the connectivity. Define :py:meth:`~kaiju_app.app.Service.init` and :py:meth:`~kaiju_app.app.Service.close`
methods. You may also want to create :py:meth:`~kaiju_app.app.Service.get_health` for some basic health checks.

You will also need to provide connection settings for your Redis pool. The best way is to include such settings in
the `__init__` method as input arguments, so they could be provided in a config file. Note that in the example below
a *dataclass* was used. Usage of dataclasses in services is recommended but not mandatory.

.. code-block:: python
  :caption: app/cache.py

    from dataclasses import dataclass, field
    from time import time
    from coredis import Redis
    from kaiju_app import Service, Health, wrap_exception

    @dataclass(kw_only=True)
    class RedisCache(Service):

        conn_settings: dict
        _client: Redis = field(init=False)

        async def get(self, key: str) -> object | None: ...

        async def set(self, key: str, value: object) -> None: ...

        async def init(self) -> None:
            self._client = Redis(**self.conn_settings)

        async def close(self) -> None:
            self._client = None

        async def get_health(self) -> Health:
            t0 = time()
            try:
                await self._client.execute_command(b'INFO')
            except Exception as e:
                return Health(healthy=False, stats={'ping': None}, errors=[wrap_exception(e)])
            else:
                return Health(healthy=True, stats={'ping': time() - t0}, errors=[])

Now when you have `init()` and `close()` set, the client and connection pool will be automatically created at startup.

.. note::

  Both `init()` and `close()` methods have their maximum timeout defined by the application
  :py:attr:`~kaiju_app.app.Application.service_start_timeout_s`. The service will fail if the timeout is
  reached.

Post-initialization
^^^^^^^^^^^^^^^^^^^

Imagine that you created the cache and the product service as mentioned in the previous chapter. However you have to
check whether the product cache exists on startup and if not you must load it into the cache. This operation may
be time consuming. You can put it in `init()` but this means that the app cannot start until the operation is completed.
This may cause the orchestrator (such as docker) prematurely kill the container on time limit.

To avoid that the service API provides :py:meth:`~kaiju_app.app.Service.post_init` interface which is called directly
after the app start.

.. code-block:: python
  :caption: app/products.py

    from dataclasses import dataclass
    from kaiju_app import service, Service
    from app.cache import RedisCache

    @dataclass(kw_only=True)
    class ProductInfo(Service):

        cache: RedisCache = service()

        async def get_product(self, id: str) -> object | None:
            product = await self.cache.get(f'product.{id}')
            if product is not None:
                return product
            product = await self.products_table.select().where(id=id)
            return product

        async def post_init(self) -> None:
            async for product in self.product_table.iter():
                product_id = f'product.{product["id"]}'
                if not await self.cache.get(product_id):
                    await self.cache.set(product_id, product)

.. note::

  `post_init()` also has a maximum timeout determined by the application
  :py:attr:`~kaiju_app.app.Application.post_init_timeout_s`. The post-init task will be cancelled if the timeout
  is reached. The service will continue its operation nonetheless.

Optional dependencies
^^^^^^^^^^^^^^^^^^^^^

Suppose you have a service which is not required and may not be present in the app. You can set it as an optional
dependency by setting `required=False` in the service field. However, it also requires you to check whether a service
is present and available when you need to use it. See the example below.

.. code-block:: python
  :caption: app/products.py

    @dataclass(kw_only=True)
    class ProductInfo(Service):

        cache: RedisCache = service(required=False)

        async def get_product(self, id: str) -> object | None:
            if self.cache:  # check if the service is available
              product = await self.cache.get(f'product.{id}')
              if product is not None:
                  return product
            product = await self.products_table.select().where(id=id)
            return product

Note that this also would require some config tweaks (see :ref:`config specs <config-spec>` for detail). For example,
you may want to make your cache optional and enable / disable it by setting a special variable.

.. code-block:: yaml
  :caption: settings/config.yaml

  app:
    services:
      - cls: RedisCache
        enabled: "[cache_enable:True]"
        settings:
          host: 0.0.0.0
          port: 6379
      - cls: ProductInfo

Another option would be to make the cache *optional*. This means that if it fails to start it will be skipped and the app
proceeds without it. This is more like a fail-safe mechanism and the first method should be preferred.

.. code-block:: yaml
  :caption: settings/config.yaml

  app:
    optional_services:
      - RedisCache
    services:
      - cls: RedisCache
        settings:
          host: 0.0.0.0
          port: 6379
      - cls: ProductInfo

Dependency cycle
^^^^^^^^^^^^^^^^

When adding your services you may encounter this type of error.

.. code-block::

  >           raise DependencyCycleError(
                  f"Dependency cycle detected in services: {exc.args[1]}\n\n"
                  "Fix: Use nowait=True in `service` fields for dependencies to manually resolve the cycle."
              ) from None
  E           kaiju_app.loader.DependencyCycleError: Dependency cycle detected in services: ['A', 'B', 'A']
  E
  E           Fix: Use nowait=True in `service` fields for dependencies to manually resolve the cycle.

Don't get mad! It just means that you created two services which explicitly or implicitly depend on each other.
Here's a simplified example of this.

.. code-block:: python

  class MyService(Service):
    dep: 'MyOtherService' = service()

  class MyOtherService(Service):
    dep: 'MyService' = service()

It create a dependency cycle and the application loader can't know which service must be initialized first. To prevent
this you should manually break the cycle by setting `nowait=True` for one of the dependencies.

.. code-block:: python

  class MyService(Service):
    dep: 'MyOtherService' = service()

  class MyOtherService(Service):
    dep: 'MyService' = service(nowait=True)

Dependency not found
^^^^^^^^^^^^^^^^^^^^

Suppose you see an error like this.

.. code-block::

  >           raise DependencyNotFound(
                  f"Dependency failed for service: {service_.name}\n\n"
                  f"Fix: Check if a service {name} of type {field_.type} is present in the config."
              ) from None
  E           kaiju_app.loader.DependencyNotFound: Dependency failed for service: b
  E
  E           Fix: Check if a service ... of type <class 'test_app_loader_resolve_dependencies._ServiceWithCircularDepA'> is present in the config.

It only means that you haven't added your service class to the map of service classes, and the application loader thus
can't create a service. The solution is simple to register your service class.
