import asyncio

import pytest

from kaiju_app.server import Server
from kaiju_app.errors import Cancelled, ServiceNotAvailable

from uvlog import get_logger


@pytest.mark.asyncio
class TestServer:

    @pytest.fixture(autouse=True)
    def _loop(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)

    def test_json_repr(self):
        server = Server(logger=get_logger())
        print(server.json_repr())

    async def test_valid_call(self):
        service = pytest.TestClass(0.001)
        params = {'value': True}
        async with Server(logger=get_logger()) as server:
            task = await server.call(service.run, kws=params)
            args, kws = await task
            assert kws == params

    async def test_retries(self):
        service = pytest.TestClass(0.001)
        async with Server(logger=get_logger()) as server:
            task = await server.call(service.retry, kws={'retries': 3}, retries=3, retry_interval_s=0)
            result = await task
            assert result == 3

    async def test_retries_batch(self):
        service = pytest.TestClass(0.001)
        batch = [
            (service.run, [], {'value': 0}),
            (service.retry, [], {'retries': 3})
        ]
        async with Server(logger=get_logger()) as server:
            task = await server.call_many(batch, retries=3, retry_interval_s=0)
            result = await task
            assert result[1] == 3

    async def test_valid_batch_calls(self):
        service = pytest.TestClass(0.001)
        async with Server(logger=get_logger()) as server:
            task = await server.call_many([
                (service.run, [], {'value': 0}),
                (service.run, [], {'value': 1}),
                (service.run, [], {'value': 2}),
            ])
            result = await task
            assert [r[1]['value'] for r in result] == [0, 1, 2]

    async def test_timeout(self):
        service = pytest.TestClass(1)
        async with Server(logger=get_logger()) as server:
            task = await server.call(service.run, kws={}, request_timeout_s=0.01)
            result = await task
            assert isinstance(result, asyncio.TimeoutError)

    async def test_batch_timeout(self):
        service = pytest.TestClass(0.006)
        async with Server(logger=get_logger()) as server:
            task = await server.call_many([
                (service.run, [], {'value': 0}),
                (service.run, [], {'value': 1}),
                (service.run, [], {'value': 2}),
                (service.run, [], {'value': 3}),
            ], request_timeout_s=0.01)
            result = await task
            for _result in result[1:]:
                assert isinstance(_result, asyncio.TimeoutError), 'all subsequent requests must me cancelled'

    async def test_callback(self):
        service = pytest.TestClass(0.001)
        async with Server(logger=get_logger()) as server:
            task = await server.call(service.run, kws={}, callback=service.run)
            await task
            assert service.counter == 2, 'callback must be called'

    async def test_batch_callback(self):
        service = pytest.TestClass(0.001)
        batch = ((service.run, [], {}), (service.run, [], {}))
        async with Server(logger=get_logger()) as server:
            task = await server.call_many(batch, callback=service.run)
            await task
            assert service.counter == len(batch) + 1, 'callback must be called exactly once for the whole batch'

    async def test_server_full(self):
        server = Server(logger=get_logger())
        server.max_parallel_tasks = 1
        service = pytest.TestClass(0.001)
        async with server:
            server.call_nowait(service.run, kws={})
            with pytest.raises(asyncio.QueueFull):
                server.call_nowait(service.run, kws={})

    async def test_server_full_batch(self):
        server = Server(logger=get_logger())
        server.max_parallel_tasks = 1
        service = pytest.TestClass(0.001)
        async with server:
            server.call_many_nowait((service.run, [], {}),)
            with pytest.raises(asyncio.QueueFull):
                server.call_many_nowait((service.run, [], {}),)

    async def test_batch_abort(self):
        service = pytest.TestClass(0.006)
        async with Server(logger=get_logger()) as server:
            task = await server.call_many([
                (service.run, [], {'value': 0}),
                (service.fail, [], {'value': 1}),
                (service.run, [], {'value': 2}),
                (service.run, [], {'value': 3}),
            ], abort_batch_on_error=True)
            result = await task
            assert not isinstance(result[0], Exception)
            assert isinstance(result[1], Exception)
            for _result in result[2:]:
                assert isinstance(_result, Cancelled), 'all subsequent requests must me aborted'

    async def test_server_full_async(self):
        pass

    async def test_server_closed(self):
        server = Server(logger=get_logger())
        service = pytest.TestClass(0.001)
        with pytest.raises(ServiceNotAvailable):
            server.call_nowait(service.run, kws={})

    async def test_server_closed_batch(self):
        server = Server(logger=get_logger())
        service = pytest.TestClass(0.001)
        with pytest.raises(ServiceNotAvailable):
            server.call_many_nowait(((service.run, [], {}),))

    async def test_server_closed_async(self):
        server = Server(logger=get_logger())
        service = pytest.TestClass(0.001)
        with pytest.raises(ServiceNotAvailable):
            await server.call(service.run, kws={})

    async def test_server_closed_batch_async(self):
        server = Server(logger=get_logger())
        service = pytest.TestClass(0.001)
        with pytest.raises(ServiceNotAvailable):
            await server.call_many(((service.run, [], {}),))
