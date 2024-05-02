"""App configuration module."""

import argparse
import os
from typing import Any

from kaiju_app.loader import AppConfig, ProjectConfig, ServiceConfig
from kaiju_app.utils import Template, eval_string, merge_dicts

__all__ = ["Configurator", "default_argument_parser"]


default_argument_parser = argparse.ArgumentParser()
default_argument_parser.add_argument(
    "-e",
    "--env",
    dest="env",
    default=[],
    metavar="KEY=VALUE",
    action="append",
    help="specify environment variable (may be used multiple times)",
)


class Configurator:
    """Configuration loader.

    This class helps to prepare configuration dict from a list of configuration files.

    >>> template  = {'app': {'name': '[_doctest_app_name]', 'env': '[_doctest_app_env]'}}
    >>> env = {'_doctest_app_name': 'app', '_doctest_app_env': 'prod'}
    >>> configurator = Configurator()
    >>> configurator.create_configuration([template], [env])
    {'debug': False, 'packages': [], 'logging': {}, 'app': {'name': 'app', 'env': 'prod', 'loglevel': None, \
'settings': {}, 'scheduler': {}, 'server': {}, 'optional_services': [], 'services': []}}

    """

    def create_configuration(
        self,
        templates: list[dict[str, Any]],
        envs: list[dict[str, Any]],
        *,
        load_os_env: bool = False,
        load_cli_env: bool = False,
    ) -> ProjectConfig:
        """Create a project configuration from template and environment data.

        Usually you would store configs in config files. Load them using an appropriate method (json or yaml loader)
        and then pass to `templates` and `envs` arguments.

        Initialization order:

        1. Merge templates from first to last
        2. Merge env dicts from first to last
        3. Load OS environment variables
        4. Load CLI environment variables from '--env' flags
        5. Evaluate template using resulting env dict
        6. Normalize and return the project config dict

        See :py:func:`~kaiju_app.utils.merge_dicts` function on the rules of how dictionaries are merged.

        See the `template-dict documentation <http://template-dict.readthedocs.io>`_ on template syntax.

        """
        template = Template(merge_dicts(*templates))
        envs = [*envs]
        if load_os_env:
            envs.append(self.get_os_env(template))
        if load_cli_env:
            envs.append(self.get_cli_env(template))
        env = merge_dicts(*envs)
        config_dict = template.eval(env)
        return self.create_project_config(config_dict)

    @staticmethod
    def get_os_env(template: Template, /) -> dict:
        os_env = {}
        for key in template.keys:
            value = os.getenv(key)
            if value:
                value = eval_string(value)
                os_env[key] = value
        return os_env

    @staticmethod
    def get_cli_env(template: Template, parser: argparse.ArgumentParser = default_argument_parser) -> dict:
        cli_env = {}
        ns, _ = parser.parse_known_args()
        for env_value in ns.env:
            key, value = env_value.split("=")
            key, value = key.strip(), value.strip()
            value = eval_string(value)
            if key in template.keys:
                cli_env[key] = value
        return cli_env

    @staticmethod
    def create_project_config(config_dict: dict, /) -> ProjectConfig:
        app_config = config_dict["app"]
        services_config = app_config.get("services", [])
        services_config = [
            ServiceConfig(
                cls=service_config["cls"],
                name=service_config.get("name", service_config["cls"]),
                loglevel=service_config.get("loglevel", None),
                enabled=service_config.get("enabled", True),
                settings=service_config.get("settings", {}),
            )
            for service_config in services_config
        ]
        app = AppConfig(
            name=app_config["name"],
            env=app_config["env"],
            loglevel=app_config.get("loglevel", None),
            settings=app_config.get("settings", {}),
            scheduler=app_config.get("scheduler", {}),
            server=app_config.get("server", {}),
            optional_services=app_config.get("optional_services", []),
            services=services_config,
        )
        return ProjectConfig(
            debug=config_dict.get("debug", False),
            packages=config_dict.get("packages", []),
            logging=config_dict.get("logging", {}),
            app=app,
        )
