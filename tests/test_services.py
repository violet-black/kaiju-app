import asyncio

import pytest
import uvlog

from kaiju_app.app import Application, Service, ServiceState, APP_CONTEXT, Health


class _Service(Service):

    def __init__(self, *args, init_f=None, close_f=None, health_f=None, post_init_f=None, **kws):
        super().__init__(*args, **kws)
        self.init_f = init_f
        self.close_f = close_f
        self.health_f = health_f
        self.post_init_f = post_init_f
        self.post_init_called = False

    async def init(self) -> None:
        if self.init_f is not None:
            await self.init_f()

    async def close(self) -> None:
        if self.close_f is not None:
            await self.close_f()

    async def post_init(self):
        if self.post_init_f:
            await self.post_init_f()
        self.post_init_called = True

    async def get_health(self):
        h = Health(healthy=True, stats={}, errors=[])
        if self.health_f is not None:
            try:
                await self.health_f()
            except Exception as exc:
                h['errors'].append(str(exc))
                h['healthy'] = False
        return h

    def get_context_var(self, key):
        return self.app.get_context_var(key)


async def _f_err():
    raise RuntimeError('Internal error')


async def _f_timeout():
    await asyncio.sleep(1)


_logger = uvlog.get_logger()
_logger.set_level('DEBUG')
_logger.handlers[0].formatter.format = '{name} {message} {extra}'  # noqa


@pytest.mark.asyncio
class TestServices:

    async def test_initialization(self):
        service_ = _Service(app=None, name='_Service', logger=_logger)
        print(str(service_))
        assert service_.state.is_(ServiceState.CLOSED)
        async with service_:
            assert service_.state.is_(ServiceState.READY)
        assert service_.state.is_(ServiceState.CLOSED)

    @pytest.mark.parametrize(
        'service_',
        [
            _Service(app=None, name='_Service', logger=_logger, health_f=_f_err),
            _Service(app=None, name='_Service', logger=_logger, init_f=_f_err)
        ],
        ids=[
            'unhealthy',
            'error on init'
        ]
    )
    async def test_initialization_failed(self, service_):
        assert service_.state.is_(ServiceState.CLOSED)
        with pytest.raises(RuntimeError):
            async with service_:
                assert service_.state.is_(ServiceState.READY)
        assert service_.state.is_(ServiceState.CLOSED)


@pytest.mark.asyncio
class TestApplication:

    @pytest.fixture
    def _app(self):
        return Application(
            name='test_app', env='pytest', logger=_logger, context=APP_CONTEXT, service_start_timeout_s=0.01,
            post_init_timeout_s=0.01)

    async def test_initialization(self, _app):
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _service_2 = _Service(app=_app, name='_Service_2', logger=_logger.get_child('_Service_2'))
        _app.add_services(_service_1, _service_2)
        async with _app:
            await asyncio.sleep(0.1)
            for _service in (_service_1, _service_2):
                assert _service.name in _app.services
                assert _service.state.is_(ServiceState.READY)
                assert _service.post_init_called

            inspection = await _app.inspect()
            print(inspection)
            assert inspection['health']['healthy']

        for _service in _app.services.values():
            assert _service.state.is_(ServiceState.CLOSED), 'all services must be closed on exit'

    @pytest.mark.parametrize(
        'faulty_service_',
        [
            _Service(app=None, name='_Service', logger=_logger.get_child('faulty_service'), health_f=_f_err),
            _Service(app=None, name='_Service', logger=_logger.get_child('faulty_service'), init_f=_f_err),
            _Service(app=None, name='_Service', logger=_logger.get_child('faulty_service'), init_f=_f_timeout),
        ],
        ids=[
            'unhealthy',
            'error on init',
            'init timeout',
        ]
    )
    async def test_initialization_failed(self, _app, faulty_service_):
        faulty_service_.app = _app
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _app.add_services(_service_1, faulty_service_)
        with pytest.raises(RuntimeError):
            async with _app:
                pass
        for _service in _app.services.values():
            assert _service.state.is_(ServiceState.CLOSED), 'all services must be closed on exit'

    @pytest.mark.parametrize(
        'faulty_service_',
        [
            _Service(app=None, name='_Faulty', logger=_logger.get_child('faulty_service'), close_f=_f_err),
            _Service(app=None, name='_Faulty', logger=_logger.get_child('faulty_service'), close_f=_f_timeout),
            _Service(app=None, name='_Faulty', logger=_logger.get_child('faulty_service'), post_init_f=_f_err),
            _Service(app=None, name='_Faulty', logger=_logger.get_child('faulty_service'), post_init_f=_f_timeout),
        ],
        ids=[
            'error on close',
            'timeout on close',
            'error on post init',
            'timeout on post init',
        ]
    )
    async def test_handled_initialization_failures(self, _app, faulty_service_):
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _app.add_services(_service_1, faulty_service_)
        async with _app:
            await asyncio.sleep(0.01)
        assert _service_1.state.is_(ServiceState.CLOSED), 'other service must be closed'

    async def test_optional_service_failure(self, _app):
        faulty_service_ = _Service(app=_app, name='_Faulty', logger=_logger.get_child('_Faulty'), init_f=_f_err)
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _app.add_services(_service_1, faulty_service_)
        _app.optional_services = ['_Faulty']
        async with _app:
            await asyncio.sleep(0.01)
            assert _service_1.state.is_(ServiceState.READY), 'other service must be initialized'
        assert _service_1.state.is_(ServiceState.CLOSED), 'other service must be closed'

    async def test_post_init_failures(self, _app):
        faulty_ =  _Service(app=_app, name='_Faulty', logger=_logger.get_child('_Faulty'), post_init_f=_f_err)
        timed_ =  _Service(app=_app, name='_Timed', logger=_logger.get_child('_Timed'))
        timed_.post_init = lambda: asyncio.sleep(1.0)
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _app.add_services(_service_1, faulty_, timed_)
        async with _app:
            await asyncio.sleep(0.01)
            assert _service_1.post_init_called is True, 'post init must be called for other services'

    async def test_context_vars(self, _app):
        _service_1 = _Service(app=_app, name='_Service_1', logger=_logger.get_child('_Service_1'))
        _app.add_services(_service_1)
        async with _app:
            _app.set_context_var('foo', 'bar')
            assert _service_1.get_context_var('foo') == 'bar'
            _app.set_context_var('foo', 'foo')
            assert _service_1.get_context_var('foo') == 'foo'
            assert _app.get_context_var('not exists') is None
