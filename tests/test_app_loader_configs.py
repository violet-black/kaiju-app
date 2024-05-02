from dataclasses import dataclass

import pytest

from kaiju_app.app import Service, service, Application
from kaiju_app.loader import ApplicationLoader, ProjectConfig, AppConfig, ServiceConfig, ServiceNameConflict, ConfigurationError


@dataclass
class _ServiceA(Service):
    param: str


@dataclass
class _ServiceB(Service):
    dependency: _ServiceA = service()


class _ServiceNoDataclass(Service):
    dependency: _ServiceA = service()


class TestAppLoaderConfigs:

    @pytest.fixture
    def _loader(self):
        _types = {
            '_ServiceA': _ServiceA,
            '_ServiceB': _ServiceB
        }
        return ApplicationLoader(service_classes=_types)

    @pytest.fixture
    def _default_config(self):
        return ProjectConfig(
            debug=True,
            packages=[],
            logging={},
            app=AppConfig(
                name='test',
                loglevel='INFO',
                env='pytest',
                settings={
                    'metadata': {'param': 'test'},
                },
                scheduler={},
                server={},
                optional_services=[],
                services=[
                    ServiceConfig(
                        cls='_ServiceA',
                        name='enabled_service',
                        loglevel='ERROR',
                        enabled=True,
                        settings={
                            'param': 'test'
                        }
                    ),
                    ServiceConfig(
                        cls='_ServiceA',
                        name='disabled_service',
                        loglevel='ERROR',
                        enabled=False,
                        settings={}
                    )
                ]
            )
        )

    def test_configurations(self, _loader, _default_config):
        app = _loader.create_all(Application, _default_config)
        assert app.name == 'test'
        assert app.env == 'pytest'
        assert app.logger.level == 'INFO'
        assert app.metadata['param'] == 'test'
        assert 'enabled_service' in app.services, 'enabled service must be created'
        assert 'disabled_service' not in app.services, 'disabled service must be skipped'
        _service = app.services['enabled_service']
        assert _service.name == 'enabled_service'
        assert _service.logger.level == 'ERROR'

    def test_name_conflict(self, _loader, _default_config):
        _default_config['app']['services'][0]['name'] = 'same_name'
        _default_config['app']['services'][1]['name'] = 'same_name'
        _default_config['app']['services'][1]['enabled'] = True
        with pytest.raises(ServiceNameConflict):
            _loader.create_all(Application, _default_config)

    def test_configuration_error(self, _loader, _default_config):
        _default_config['app']['services'][0]['settings'].clear()
        with pytest.raises(ConfigurationError):
            _loader.create_all(Application, _default_config)

    def test_configuration_invalid_class(self, _loader, _default_config):
        _default_config['app']['services'][0]['cls'] = '_UnknownClass'
        with pytest.raises(ConfigurationError):
            _loader.create_all(Application, _default_config)

    def test_configuration_not_a_dataclass(self, _loader, _default_config):
        _default_config['app']['services'][1]['cls'] = '_ServiceNoDataclass'
        _default_config['app']['services'][1]['enabled'] = True
        with pytest.raises(ConfigurationError):
            app = _loader.create_all(Application, _default_config)
            assert app.services['_ServiceNoDataclass'].dependency is app.services['_ServiceA']
