.. _scheduler:

:tocdepth: 2

**scheduler** - execute internal methods periodically
-----------------------------------------------------

You can schedule periodic asyncio tasks in your app internally using a simple task scheduler provided by this library.
The scheduler manages task state, restarts, timeouts and allows to temporarily suspend and resume tasks. It also
provides a single endpoint for all periodic routines in your app.

By default the :py:class:`~kaiju_app.scheduler.Scheduler` is available via `app.scheduler` attribute.
Use :py:meth:`~kaiju_app.scheduler.Scheduler.schedule_task` to create a new task. The task will be automatically
set for execution, and the method itself returns a :py:class:`~kaiju_app.scheduler.ScheduledTask` object.

.. code-block:: python

    @dataclass
    class CacheService(Service):

        _recache_task: ScheduledTask = field(init=False)

        async def init(self)
            self._recache_task = self.app.scheduler.schedule_task(self._recache_all, interval_s=3600)

        async def recache_all(self) -> None:
            ...

The task will be automatically started once the app is ready. The scheduler guarantees that each task is run at most
once simultaneously without creating multiple concurrent runs of the same task. For more information on task execution
policies see :py:class:`~kaiju_app.scheduler.ExecPolicy`.

There's a suspend mechanism which you can use in your services to prevent the task from running while a certain
operation is taking place. The task will not be scheduled until the program exits the context.

.. code-block:: python

    async def update_cache(self) -> None:
        async with self._recache_task.suspend():
            ...

.. attention::

    Task suspend mechanism of course doesn't take in account that there may be multiple instances of your app running at
    the same time.

.. autoclass:: kaiju_app.scheduler.Scheduler
   :members:
   :undoc-members:

.. autoclass:: kaiju_app.scheduler.ScheduledTask
   :members:
   :exclude-members: __init__

.. autoclass:: kaiju_app.scheduler.ExecPolicy
   :members:
   :undoc-members:
   :show-inheritance:
