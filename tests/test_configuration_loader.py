import sys
from dataclasses import dataclass

import pytest

from kaiju_app.app import Service, Application
from kaiju_app.configurator import Configurator
from kaiju_app.loader import ApplicationLoader


@dataclass
class _Service(Service):
    value: str


class TestConfigurationLoader:

    @pytest.fixture
    def _configurator(self):
        configurator = Configurator()
        return configurator

    @pytest.fixture
    def _config_minimal(self):
        return {
            'app': {
                'name': '[app_name]',
                'env': '[app_env]'
            }
        }

    def test_minimal_configuration(self, _configurator, _config_minimal):
        env = {
            'app_name': 'app',
            'app_env': 'pytest'
        }
        config = _configurator.create_configuration(
            [_config_minimal], [env], load_os_env=False, load_cli_env=False)
        print(config)
        assert config['app']['name'] == 'app'
        assert config['app']['env'] == 'pytest'

    def test_cli_env(self, monkeypatch, _configurator, _config_minimal):
        env = {
            'app_env': 'something'
        }
        with monkeypatch.context() as ctx:
            ctx.setattr(sys, 'argv', [sys.argv[0], '--env', 'app_name=app', '-e', 'app_env=pytest'])
            config = _configurator.create_configuration(
                [_config_minimal], [env], load_os_env=False, load_cli_env=True)
        print(config)
        assert config['app']['name'] == 'app'
        assert config['app']['env'] == 'pytest'

    def test_os_env(self, monkeypatch, _configurator, _config_minimal):
        env = {
            'app_env': 'pytest'
        }
        monkeypatch.setenv('app_name', 'app')
        config = _configurator.create_configuration(
            [_config_minimal], [env], load_os_env=True, load_cli_env=False)
        print(config)
        assert config['app']['name'] == 'app'
        assert config['app']['env'] == 'pytest'

    def test_with_app_loader(self, _configurator, _config_minimal):
        loader = ApplicationLoader()
        loader.service_classes['_Service'] = _Service
        _config_minimal['app']['services'] = [{
            'cls': '_Service',
            'settings': {
                'value': 'test'
            }
        }]
        env = {
            'app_name': 'app',
            'app_env': 'pytest'
        }
        config = _configurator.create_configuration(
            [_config_minimal], [env], load_os_env=False, load_cli_env=False)
        app = loader.create_all(Application, config)
        assert '_Service' in app.services
