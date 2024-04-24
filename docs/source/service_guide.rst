.. _service-guide:

How to use services
===================

*Service* is a building block of an application. It's a class implementing particular encapsulated logic. The difference
between a service and just a class is that a service has initialization mechanism and state, so it can be initialized
and monitored by an app. It also means that other services may wait for its initialization and access it using the app
internal router.

Create a service
----------------

The idea behind a service is that it should be application-independent, allowing it to be a part of any application as
long as its dependency services are also provided.

To create a service use a base :py:class:`~kaiju_app.app.Service` class.

.. code-block:: python

    from datetime import datetime
    from kaiju_app import Service

    class TimeService(Service):

        def get_current_time(self) -> datetime:
            return datetime.now()

Once you created an app (see :ref:`app-guide`) and initialized the services you can now access this service by its name
from other services using the internal :py:attr:`~kaiju_app.app.Application.services` router.

.. code-block:: python

    class UserService(Service):

        async def create_user(self, user_data: dict) -> None:
            _data = {
                **user_data,
                'created': self.app['TimeService'].get_current_time()
            }
            ...

There are a few flaws in using this simple methods though. First you don't get hints in IDE. Second it's easy to make
a typo here. Finally, the dependency service may not be yet initialized or even present! To counter this issues
there's a dependency resolver mechanism built on top of Python *dataclasses*.

.. note::

    Services are referenced by their *names* which by default are the same as their class names. However one may
    specify a different *name* when initializing a service or in a config file. This is to allow multiple services
    of the same class to coexist and be selected based on their unique names (for example: two coexistent
    connectors to different databases).

Use dependencies
----------------

Use a special :py:func:`~kaiju_app.app.Application.service` field and add a type hint to specify a dependency in your
service.

.. code-block:: python

    from dataclasses import dataclass

    @dataclass
    class UserService(Service):
        time_service: TimeService = service()
        # time_service: 'TimeService' = service()  # you can use string references here too

        async def create_user(self, user_data: dict) -> None:
            _data = {
                **user_data,
                'created': self.time_service.get_current_time()
            }
            ...

The resolver ensures that the other service will be initialized and ready before starting the dependent one.

But what if I have a case where one service requires another and that service in case requires the first one, creating
a dependency cycle? The resolver won't allow such situation and :py:class:`~kaiju_app.loader.DependencyCycleError`
will be produced. There's no way for the resolver to know which of two services actually needs other first for its
initialization.

However there's still a way to resolve the dependency cycle manually. Use `nowait=True` in one of your services to
tell the resolver that you don't need to wait for this dependency to start before initializing the service. If you have
to be sure that the dependency actually started before executing a particular method use
:py:meth:`~kaiju_app.app.Service.wait`.

.. code-block:: python

    @dataclass
    class UserService(Service):
        permissions: 'PermissionService' = service()

    @dataclass
    class GroupService(Service):
        users: 'UserService' = service(nowait=True)

        async def delete_group(self, group_id: str) -> None:
            await self.users.wait()  # you may use this in a particular method
            await self.users.update(where={'group_id': group_id}, values={'group_id': None})
            ...

You can also create a dependency which is not required. In that case if there's no such dependency it will be set
to `None` by the resolver. You can check whether the service is available in your methods by calling `is None` for it.

.. code-block:: python

    @dataclass
    class UserService(Service):
        cache: 'CacheService' = service(required=False)

        async def get_user(self, user_id: str) -> User:
            if self.cache:
                user = await self.cache.get(f'user.{user_id}')
            ...

A *named dependency* is when you provide not only a class but also a particular name for the service. A named dependency
won't match a service unless it has the same name as specified.

.. code-block:: python

    @dataclass
    class UserService(Service):
        cache: 'CacheService' = service(required=False, name='user_cache')

Initialize asynchronously
-------------------------

But what is this *initialization* exactly? It's simple. Imagine you have a service which has a database pool or a TCP
connection which must be ready before all the service method can actually work. The service API provides you with
:py:meth:`~kaiju_app.app.Service.init` and :py:meth:`~kaiju_app.app.Service.close` which are guaranteed to be run by
the app on app start and on exit. There's also a handy interface :py:meth:`~kaiju_app.app.Service.get_health` for
service health status. See the example below.

.. code-block:: python

    from dataclasses import dataclass, field
    from time import time
    from kaiju_app import Service, Health

    @dataclass
    class DatabaseService(Service):
        host: str
        port: int
        _conn_pool: db.Pool = field(init=False)

        async def init(self):
            self._conn_pool = await db.create_pool(self.host, self.port)

        async def close(self):
            await self._conn_pool.close()
            self._conn_pool = None

        async def get_health(self) -> Health:
            try:
                t0 = time()
                await self._conn_pool.execute('SELECT 1')
                t_ping = time() - t0
            except Exception as exc:
                return Health(healthy=False, stats={}, errors=[str(exc)])
            else:
                return Health(healthy=True, stats={'ping': t_ping}, errors=[])

What if you need some bulky procedure what takes a lot of time and could really slow down the start process? Ideally you
should probably use some task or CI system for this. However the API provides :py:meth:`~kaiju_app.app.Service.post_init`
method which is executed *after* the application started and can be used to initialize cache or do some other time
consuming operations.

.. code-block:: python

    from asyncio import Event

    @dataclass
    class LocalCache(Service):
        _cache_loaded: Event = Event()

        async def post_init(self):
            self._cache_loaded.clear()
            await self.load_all_cache_from_redis()
            self._cache_loaded.set()

.. note::

    Both *init* and *close* and *post_init* have their time limits for each service specified in the application.
    See :py:attr:`~kaiju_app.app.Application.service_start_timeout_s`
    and :py:attr:`~kaiju_app.app.Application.service_start_timeout_s`.
    Note however that environments such as Docker may have their own idea about time limits and *will* kill the container
    if it takes too long to initialize. Keep that in mind when modifying the *service_start_timeout_s* limit.

Logs and contextvars
--------------------

The application loader provides each service with an unique logger. Currently our custom
`uvlog <http://uvlog.readthedocs.io>`_ library is used for logging.

.. code-block:: python

    class UserService(Service):

        async def block_user(self, user_id: str) -> None:
            ...
            self.logger.info('User is blocked', user_id=user_id)

The log context using Python *contextvars* is supported and can be very useful when aggregating logs for method call
chains.

.. code-block:: python

    class AdminPanel(Service):
        users: 'UserService' = service()

        async def block_user(self, admin: str, user_id: str) -> None:
            self.app.set_context_var('admin', admin)
            await self.check_permissions(admin)
            await self.users.block_user(user_id)

    class UserService(Service):

        async def block_user(self, user_id: str) -> None:
            ...
            self.logger.info('User is blocked')  # the logger will have 'admin' name in this message context

.. attention::

    Do not ever use the app *contextvars* to pass method parameters between services.
    This is not what this mechanism is for, and you will make your life much more complicated by doing so.

Schedule periodic tasks
-----------------------

The application has an internal :py:attr:`~kaiju_app.app.Application.scheduler` which can be used by services to
create periodic asyncio tasks and manage them. The scheduler uses our `kaiju-scheduler <http://kaiju-scheduler.readthedocs.io>`_
library. See its documentation on how to use and manipulate tasks. Here's just a brief example.

.. code-block:: python

    @dataclass
    class CacheService(Service):
        ...
        _cache_update_task: ScheduledTask = None

        def __post_init__(self):
            self._cache_update_task = self.app.scheduler.schedule_task(self.reload_cache, interval=600)

        async def reload_cache(self) -> None:
            ...

        async def reconnect(self) -> None:
            with self._cache_update_task.suspend():
                ...

.. note::

     The scheduler is available immediately on creating an app. However tasks are started only after each service has started.

Inspection
----------

Besides :py:meth:`~kaiju_app.app.Service.get_health` health metrics
there is a builtin interface called :py:meth:`~kaiju_app.app.Service.json_repr` where you can specify any of service
settings which should be available for inspection. The idea is that an administrator can review an app settings
for each service via :py:meth:`~kaiju_app.app.Application.inspect` which itself would call
:py:meth:`~kaiju_app.app.Service.json_repr` for each service.

.. code-block:: python

    class CacheService(Service):

        def json_repr(self):
            return {
                'max_size': self.max_size,
                'default_ttl_s': self.default_ttl_s
            }

However you shouldn't probably put passwords and other secrets in there even if the inspect API is private.
