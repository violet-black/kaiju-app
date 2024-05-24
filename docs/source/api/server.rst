.. _server:

:tocdepth: 2

**server** - execute internal methods
-------------------------------------

The :py:class:`~kaiju_app.server.Server` is not a 'real' server for external request but rather a class allowing you
to execute asynchronous functions in a more controlled way. It provides rate limiting, timeouts, retries,
callbacks and context variables for your asynchronous function.
It allows to execute such functions dynamically and thus can be used in various tasks. It mostly used for actual
client-server interactions (RPC, streams) to provide the way of calling an RPC method from the application code.

The :py:class:`~kaiju_app.server.Server` is available via `app.server` attribute. You can use when implementing
client-server interactions or any time you need a more controlled way of executing code.

There are two types of calls: single calls and batch calls.

Use :py:meth:`~kaiju_app.server.Server.call` and :py:meth:`~kaiju_app.server.Server.call_nowait` for scheduling a
single call. The latter would raise `asyncio.QueueFull` if the server queue
is full. The former would simply wait until the call is accepted by the server. Both calls return an `asyncio.Task`.
You are free either to wait for it or to ignore it — the task would be executed nonetheless.

Here's an example with waiting for the task's result.

.. code-block:: python

    @dataclass
    class MyQueueService(Service):

        async def read_from_queue(self)
            args = await self._queue.get()
            task = await self.app.server.call(self.process_value, args=args)
            result = await task

        async def write_value(self, *args) -> int:
            ...

Here's an example for using a result callback.

.. code-block:: python

        async def read_from_queue(self)
            args = await self._queue.get()
            await self.app.server.call(self.process_value, args=args, callback=self.callback_value)

        async def write_value(self, *args) -> int:
            ...

        async def callback_value(self, value_id: int | Exception) -> None:
            ...

Batch calls can be done with :py:meth:`~kaiju_app.server.Server.call_many` or
:py:meth:`~kaiju_app.server.Server.call_many_nowait` methods.

Batch calls are similar to single calls, but they consist of an iterable of multiple chained function calls and
arguments. As you can see, a batch call expects an iterable of tuples each one containing a callable, args and kwargs.

.. code-block:: python

        async def read_from_queue(self)
            batch = [(self.process_value, self._queue.get_nowait(), {}) for _ in self._queue.qsize()]
            await self.app.server.call_many(batch, callback=self.callback_values)

        async def callback_values(self, value_ids: list[int | Exception]) -> None:
            ...

The functions in a batch are executed one by one. You may request the server to abort the execution of the whole
batch on any error.

.. code-block:: python

    async def read_from_queue(self)
        batch = [...]
        task = await self.app.server.call_many(batch, abort_batch_on_error=True)

All subsequent calls in the batch will return :py:class:`~kaiju_app.errors.Cancelled` if an error happens then.

Example of results:

.. code-block:: python

    # With abort_batch_on_error=True
    [1, 2, InternalError('Something happened'), Cancelled('Cancelled by the server'), Cancelled('Cancelled by the server')]

    # Wit abort_batch_on_error=False (default)
    [1, 2, InternalError('Something happened'), 4, 5]

In case of a timeout the server will cancel all the subsequent request and set :py:class:`~kaiju_app.errors.Timeout`
for all of them since there's no way to call them anyway once the timeout is reached.

.. code-block:: python

    # Timeout example (abort_batch_on_error flag doesn't matter in this case)
    [1, 2, Timeout('Timeout'), Timeout('Timeout'), Timeout('Timeout')]


.. autoclass:: kaiju_app.server.Server
   :members:
   :undoc-members:
