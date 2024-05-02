"""Application and services loader from configuration."""

from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from graphlib import CycleError, TopologicalSorter
from importlib import import_module
from typing import Mapping, Required, TypedDict, TypeVar

import uvlog
from kaiju_scheduler import Scheduler, Server

from kaiju_app.app import APP_CONTEXT, Application, Service, ServiceFieldType

__all__ = [
    "ApplicationLoader",
    "DependencyCycleError",
    "DependencyNotFound",
    "ServiceNameConflict",
    "ConfigurationError",
    "ProjectConfig",
    "AppConfig",
    "ServiceConfig",
]

_Application = TypeVar("_Application", bound=Application)
_Service = TypeVar("_Service", bound=Service)
_SENTINEL = ...


class DependencyCycleError(RuntimeError):
    """Dependency cycle has been detected."""


class DependencyNotFound(RuntimeError):
    """Dependency service not found in the list of application services."""


class ServiceNameConflict(RuntimeError):
    """A dependency with the same name already exists."""


class ConfigurationError(RuntimeError):
    """Invalid configuration."""


class ServiceConfig(TypedDict, total=False):
    cls: Required[str]  #: service class name
    name: str  #: service custom name
    loglevel: uvlog.LevelName | None  #: service logger log level
    enabled: bool  #: enable or disable service
    settings: dict  #: args for service __init__


class AppConfig(TypedDict, total=False):
    name: Required[str]  #: application unique name
    env: Required[str]  #: application environment name: prod, test, qa, etc.
    loglevel: uvlog.LevelName | None  #: default log level for the app and app services
    scheduler: dict  #: app scheduler init settings
    server: dict  #: app server init settings
    settings: dict  #: args for application __init__
    optional_services: list[str]  #: list of optional services (names)
    services: list[ServiceConfig]  #: list of service settings


class ProjectConfig(TypedDict, total=False):
    debug: bool  #: run the project in debug mode
    packages: list[str]  #: list of service packages to import
    logging: uvlog.uvlog._DictConfig  #: loggers and handlers settings
    app: Required[AppConfig]  #: application settings


@dataclass
class ApplicationLoader:
    """Application loader class constructs an application and services from a config object.

    This class does several things to prepare the app before its start:

    1. Import services from kaiju packages using :py:meth:`~kaiju_base.app.AppLoader.import_packages`. Packages are
        imported according to the `packages` list in the config file. The services are imported into the
        :py:attr:`~kaiju_base.app.AppLoader.service_classes` class registry by their class names.
    2. Load all services using the imported packages.
    3. Resolve dependencies in :py:obj:`~kaiju_base.app.service` fields and load service instances in these attributes.
    4. Resolve service starting order according to which dependency each service has.
    5. Create an application from these services.
    """

    service_classes: dict[str, type[Service]] = field(default_factory=dict)
    """Registry of service classes."""

    allow_service_name_overrides: bool = False
    """Allow services with the same name to override each other."""

    def create_all(
        self, app_class: type[_Application], config: ProjectConfig, *, context: ContextVar[dict | None] = APP_CONTEXT
    ) -> _Application:
        """Load services from packages and return a new application."""
        self.configure_loggers(config["logging"], context)
        self.load_extensions(config["packages"])
        app = self.create_app(app_class, config["app"], context, config["debug"])
        self.init_app_services(app, config["app"]["services"])
        return app

    @staticmethod
    def configure_loggers(config: uvlog.uvlog._DictConfig, context: ContextVar[dict | None], /) -> None:
        uvlog.configure(config, context_var=context)

    def load_extensions(self, package_names: list[str], /) -> None:
        """Load services from specified packages."""
        for pkg_name in package_names:
            _module = import_module(f"{pkg_name}.services")
            for name, obj in _module.__dict__.items():
                if issubclass(obj, Service):
                    self.service_classes[name] = obj

    @staticmethod
    def create_app(
        app_class: type[_Application], config: AppConfig, context: ContextVar[dict | None], debug: bool, /
    ) -> _Application:
        app_logger = uvlog.get_logger(config["name"], persistent=True)
        loglevel = config["loglevel"]
        if loglevel is not None:
            app_logger.set_level(loglevel)
        app = app_class(
            env=config["env"],
            name=config["name"],
            context=context,
            debug=debug,
            logger=app_logger,
            optional_services=config["optional_services"],
            scheduler=Scheduler(**config["scheduler"], logger=app_logger.get_child("_scheduler")),
            server=Server(**config["server"], logger=app_logger.get_child("_server")),
            **config["settings"],
        )
        return app

    def init_app_services(self, app: _Application, config: list[ServiceConfig], /) -> None:
        app_services = self._create_app_services(app, config)
        service_loading_order = self._get_service_loading_order(app_services)
        app.add_services(*service_loading_order)

    def _create_app_services(self, app: _Application, config: list[ServiceConfig], /) -> dict[str, Service]:
        app_services = {}
        for service_config in config:
            if not service_config["enabled"]:
                continue
            if service_config["name"] in app_services and not self.allow_service_name_overrides:
                raise ServiceNameConflict(
                    f'Two services with the same name exist: {service_config["name"]}\n\n'
                    "Fix: Rename one of the services in the config or set AppLoader.allow_service_name_overrides to True to"
                    " allow overwriting services on init."
                ) from None

            if service_config["cls"] not in self.service_classes:
                raise ConfigurationError(
                    f'Service class not found: {service_config["cls"]}\n\n'
                    f"Fix: Check if the class is registered in the app loader"
                    f" `service_classes` dict and that all the required kaiju packages are listed"
                    f" in the `packages` section of the config file."
                ) from None

            new_service = self.create_service(app, self.service_classes[service_config["cls"]], service_config)
            app_services[new_service.name] = new_service

        return app_services

    @staticmethod
    def create_service(app: _Application, service_class: type[_Service], config: ServiceConfig, /) -> Service:
        service_logger = app.logger.get_child(config["name"], persistent=True)
        loglevel = config["loglevel"]
        if loglevel is not None:
            service_logger.set_level(loglevel)
        try:
            new_service = service_class(app=app, name=config["name"], logger=service_logger, **config["settings"])
        except Exception as exc:
            raise ConfigurationError(
                f'Invalid service configuration for service: {config["name"]}\n\n'
                f"Fix: check whether all required service fields"
                f" are provided in the config file and valid."
            ) from exc
        return new_service

    def _get_service_loading_order(self, app_services: dict[str, Service], /) -> list[Service]:
        dependency_map = {}
        for _service in app_services.values():
            dependency_map[_service.name] = self._load_all_service_dependencies(app_services, _service)
        dependency_map["_"] = frozenset(app_services.keys())  # root element
        dependency_tree = TopologicalSorter(dependency_map)
        try:
            loading_order: list[str] = list(dependency_tree.static_order())
        except CycleError as exc:
            raise DependencyCycleError(
                f"Dependency cycle detected in services: {exc.args[1]}\n\n"
                "Fix: Use nowait=True in `service` fields for dependencies to manually resolve the cycle."
            ) from None
        else:
            del loading_order[loading_order.index("_")]  # remove the root element
            return [app_services[name] for name in loading_order]

    def _load_all_service_dependencies(
        self, app_services: Mapping[str, Service], service_: Service, /
    ) -> frozenset[str]:
        """Load dependencies for a service and return a set of dependency names required before start."""
        dependency_names = []
        for _field in fields(service_):
            if isinstance(_field, ServiceFieldType):
                dependency = self._load_service_dependency(app_services, service_, _field)
                if dependency is not None and not _field.nowait:
                    dependency_names.append(dependency.name)
        return frozenset(dependency_names)

    def _load_service_dependency(
        self, service_map: Mapping[str, Service], service_: Service, field_: ServiceFieldType, /
    ) -> Service | None:
        """Discover and set a service dependency attribute and return it if exists."""
        name = getattr(service_, field_.name)
        if isinstance(name, Service):
            return name

        if name is _SENTINEL:
            _service_type = field_.type
            if isinstance(_service_type, str):
                _service_type = self.service_classes[_service_type]
            dependency = next(
                (srv for srv in service_map.values() if isinstance(srv, _service_type) and srv is not service_), None
            )
        else:
            dependency = service_map.get(name)
            if not isinstance(dependency, field_.type):
                dependency = None
        setattr(service_, field_.name, dependency)
        if dependency is None and field_.required:
            if name is _SENTINEL:
                name = "..."
            raise DependencyNotFound(
                f"Dependency failed for service: {service_.name}\n\n"
                f"Fix: Check if a service {name} of type {field_.type} is present in the config."
            ) from None

        return dependency
