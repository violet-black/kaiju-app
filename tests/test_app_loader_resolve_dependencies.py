import pytest
import uvlog

from dataclasses import dataclass
from kaiju_app.app import Service, service
from kaiju_app.loader import ApplicationLoader, DependencyNotFound, DependencyCycleError


_logger = uvlog.get_logger()
_logger.set_level('DEBUG')


@dataclass
class _Service(Service):
    value: str = 'test'


@dataclass
class _ServiceWithDep(Service):
    dependency: _Service = service()


@dataclass
class _ServiceWithDepStr(Service):
    dependency: '_Service' = service()


@dataclass
class _ServiceWithDepDep(Service):
    dependency: _ServiceWithDep = service()


@dataclass
class _ServiceWithSelfDep(Service):
    dependency: _ServiceWithDep = service()


@dataclass
class _ServiceWithDefaultDep(Service):
    dependency: _Service = service(name='_Custom')


@dataclass
class _ServiceWithCircularDepA(Service):
    dependency: '_ServiceWithCircularDepB' = service()


@dataclass
class _ServiceWithCircularDepB(Service):
    dependency: _ServiceWithCircularDepA = service()


@dataclass
class _ServiceWithCircularDepBNowait(_ServiceWithCircularDepB):
    dependency: _ServiceWithCircularDepA = service(nowait=True)


class TestAppLoaderResolver:

    @pytest.fixture
    def _loader(self):
        _types = {
            '_Service': _Service,
            '_ServiceWithDep': _ServiceWithDep,
            '_ServiceWithDepStr': _ServiceWithDepStr,
            '_ServiceWithDefaultDep': _ServiceWithDefaultDep,
            '_ServiceWithCircularDepA': _ServiceWithCircularDepA,
            '_ServiceWithCircularDepB': _ServiceWithCircularDepB,
            '_ServiceWithCircularDepBNowait': _ServiceWithCircularDepBNowait
        }
        return ApplicationLoader(service_classes=_types)

    @pytest.mark.parametrize(
        ['services', 'order'], (
            (
                [
                    _Service(app=None, name='a', logger=_logger),
                    _Service(app=None, name='b', logger=_logger)
                ], ['a', 'b']
            ),
            (
                [
                    _ServiceWithDepStr(app=None, name='b', logger=_logger),
                    _Service(app=None, name='a', logger=_logger)
                ], ['a', 'b']
            ),
            (
                [
                    _ServiceWithDep(app=None, name='b', logger=_logger),
                    _Service(app=None, name='a', logger=_logger),
                    _ServiceWithDepDep(app=None, name='c', logger=_logger)
                ], ['a', 'b', 'c']
            ),
            (
                [
                    _ServiceWithDep(app=None, name='b', dependency='a', logger=_logger),
                    _Service(app=None, name='a', logger=_logger),
                ], ['a', 'b']
            ),
            (
                [
                    _ServiceWithCircularDepBNowait(app=None, name='b', logger=_logger),
                    _ServiceWithCircularDepA(app=None, name='a', logger=_logger)
                ], ['b', 'a']
            ),
        ),
        ids=[
            'independent',
            'dependency hint str alias',
            'dependent',
            'named dependency',
            'circular dependency with nowait'
        ]
    )
    def test_normal_resolution(self, _loader, services, order):
        actual_order = _loader._get_service_loading_order({service_.name: service_ for service_ in services})
        actual_order = [service_.name for service_ in actual_order]
        assert actual_order == order

    @pytest.mark.parametrize(
        ['services'], (
            (
                [
                    _Service(app=None, name='a', logger=_logger),
                    _ServiceWithDepDep(app=None, name='c', logger=_logger)
                ],
            ),
            (
                [
                    _ServiceWithDep(app=None, name='b', dependency='b', logger=_logger),
                    _Service(app=None, name='a', logger=_logger),
                ],
            ),
            (
                [
                    _ServiceWithCircularDepBNowait(app=None, name='b', logger=_logger)
                ],
            )
        ),
        ids=[
            'no service',
            'no service with this name',
            'nowait dependent without dependency'
        ]
    )
    def test_dependency_not_found(self, _loader, services):
        with pytest.raises(DependencyNotFound):
            _loader._get_service_loading_order({service_.name: service_ for service_ in services})

    @pytest.mark.parametrize(
        ['services'], (
            (
                [
                    _ServiceWithCircularDepA(app=None, name='A', logger=_logger),
                    _ServiceWithCircularDepB(app=None, name='B', logger=_logger)
                ],
            ),
        )
    )
    def test_dependency_cycle(self, _loader, services):
        with pytest.raises(DependencyCycleError):
            _loader._get_service_loading_order({service_.name: service_ for service_ in services})
