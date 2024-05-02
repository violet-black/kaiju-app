"""Service and application classes."""

import asyncio
from abc import ABC
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import MISSING, Field, dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Self, TypedDict, TypeVar, final

from kaiju_scheduler import Scheduler, ScheduledTask, Server
from uvlog import Logger

from kaiju_app.bases import Error
from kaiju_app.utils import State, timeout, Namespace

__all__ = [
    "APP_CONTEXT",
    "Application",
    "service",
    "Service",
    "ServiceState",
    "ServiceFieldType",
    "Health",
    "Error",
    "ServiceInitFailed",
    "ServiceInitTimeout",
    "run_app",
    "Scheduler",
    "ScheduledTask",
]

_AsyncCallable = Callable[..., Awaitable[Any]]
_Application = TypeVar("_Application", bound="Application")
_ServiceClasses = dict[str, type["Service"]]
_SENTINEL = ...


APP_CONTEXT: ContextVar[dict | None] = ContextVar("APP_CONTEXT", default=None)
"""Application context variable."""


@final
class ServiceState(Enum):
    """Service state types."""

    CLOSED = "CLOSED"
    STARTING = "STARTING"
    READY = "READY"
    CLOSING = "CLOSING"


class Health(TypedDict):
    """Service health statistics."""

    healthy: bool  #: service is healthy
    stats: dict[str, Any]  #: reserved for stats and metrics
    errors: list[str]  #: list of error messages


class ServiceInitFailed(Error, RuntimeError):
    """Initialization of a service has failed."""


class ServiceInitTimeout(Error, RuntimeError):
    """Service is exceeded its timeout during the initialization."""


class ServiceFieldType(Field):
    """Used to store dependent service settings for other services."""

    __slots__ = ("required", "nowait")

    def __init__(self, required: bool, nowait: bool, *args):
        """Initialize."""
        super().__init__(*args)
        self.required = required
        self.nowait = nowait


def service(*, name=_SENTINEL, metadata=None, required: bool = True, nowait: bool = False):
    """Service field describing another service dependency.

    :param name: custom service name
    :param required: this dependency is required for the service to work
    :param nowait: do not wait for this service initialization
    :param metadata: additional field metadata, stored in the dataclass field

    This field provides auto-discovery for dependency services in your service. The service will try to automatically
    discover a dependency under this field and assign it to the field. This happens in service
    :py:meth:`~kaiju_base.app.Service.init` method on application start.

    Your service must be a dataclass for this to work. Then just add this field type hinting the dependency
    class.
    """
    return ServiceFieldType(required, nowait, name, MISSING, True, False, None, False, metadata, True)


@dataclass
class Service(ABC):
    """Application service - a building block for an application.

    Service is a modular part of an application. Each service must implement only specific application
    logic in a limited scope.
    """

    app: "Application"
    """Application this service is linked to."""

    name: str
    """Unique service name for referencing it in other services of the app."""

    logger: Logger
    """Logger instance."""

    state: State = field(init=False, default_factory=lambda: State(ServiceState, ServiceState.CLOSED))
    """Service state"""

    async def init(self) -> None:
        """Initialize application context.

        This method shouldn't be directly called outside the service.

        Here you should write service initialization procedures.
        It will be called through :py:meth:`~kaiju_base.app.Service.start` by the app service manager on the app
        start.
        """

    async def post_init(self):
        """Run additional scripts and commands after the :py:meth:`~kaiju_base.app.Service.start`.

        The main difference of :py:meth:`~kaiju_base.app.Service.post_init` from
        :py:meth:`~kaiju_base.app.Service.init` is that the service is considered
        :py:obj:`~kaiju_base.app.ServiceStatus.READY` when the post init is called and the app should be in working
        condition with all services initialized.

        Post init is called without any time limit unless you implement it explicitly inside the method. There's
        a global time limit on all post init tasks set by :py:attr:`~kaiju_base.app.Application.post_init_timeout_s`
        in application settings.
        """

    async def close(self) -> None:
        """Close application context.

        This method shouldn't be directly called outside the service.

        Here you should write service de-initialization procedures.
        It will be called through :py:meth:`~kaiju_base.app.Service.stop` by the app service manager on the app
        close.
        """

    def json_repr(self) -> dict:
        """Get service information for inspection or logging."""
        return {}

    async def get_health(self) -> Health:
        """Check if the service is healthy.

        Return all occurred errors in error field.
        """
        return Health(healthy=True, stats={}, errors=[])

    @final
    async def start(self) -> None:
        """Start the service.

        This method is executed on application start and when a service context is called.
        Use :py:meth:`~kaiju_app.app.Service.init` to implement custom initialization procedures and
        :py:meth:`~kaiju_app.app.Service.check_health` to check the service health afterward.
        """
        with self.state:
            self.logger.debug("starting")
            self.state.set(ServiceState.STARTING)
            await self.init()

            health = await self.get_health()
            if not health["healthy"]:
                await self.close()
                exc = RuntimeError(f'Service is not healthy: "{self.name}"')
                for error in health["errors"]:
                    exc.add_note(error)
                raise exc from None

            self.state.set(ServiceState.READY)
            self.logger.debug("started")

    @final
    async def stop(self) -> None:
        """Close application context.

        This method is executed on application exit and when a service context is called and exited.
        Use :py:meth:`~kaiju_app.app.Service.close` to implement custom de-initialization procedures.
        """
        with self.state:
            self.logger.debug("stopping")
            self.state.set(ServiceState.CLOSING)
            await self.close()
            self.state.set(ServiceState.CLOSED)
            self.logger.debug("stopped")

    async def __aenter__(self) -> Self:
        """Enter service start/stop context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit service start/stop context."""
        await self.stop()

    async def wait(self, _for_status: ServiceState = ServiceState.READY, /) -> None:
        """Wait until the service is ready."""
        await self.state.wait(_for_status)

    def __bool__(self) -> bool:
        return self.state == ServiceState.READY


@dataclass
class Application:
    """Application is a service class combining multiple other service."""

    name: str
    """Unique service name.
    Service class name is used by default by the app service manager.
    When you declare more than one service of the same type you MUST explicitly provide unique names for them."""

    logger: Logger
    """Logger instance.
    During the app init a logger instance is provided automatically by the app constructor."""

    env: str
    """App environment (scope).
    See :py:obj:`~kaiju_base.app.Environment` for a list of standard environments. It's not mandatory but recommended.
    """

    context: ContextVar[dict | None] = APP_CONTEXT
    """Context var to store a server call context."""

    debug: bool = False
    """Run app in debug mode."""

    service_start_timeout_s: float = 30.0
    """A timeout (sec) for each service start. An error will be produced if taking more than this interval."""

    post_init_timeout_s: float = 300.0
    """A post-init task timeout (sec) for ALL the services combined."""

    show_inspection_on_start: bool = False
    """Show inspection data in logs after the app start."""

    metadata: dict = field(default_factory=dict)
    """Application metadata not used by it directly."""

    optional_services: list[str] = field(default_factory=list)
    """List of optional services not required for the app start."""

    scheduler: Scheduler = field(default_factory=Scheduler)
    """Internal task scheduler."""

    server: Server = field(default_factory=Server)
    """Internal task server."""

    namespace: Namespace = field(init=False)
    """Application namespace for consistent key names across the app."""

    state: State = field(init=False, default_factory=lambda: State(ServiceState, ServiceState.CLOSED))
    """Service work state."""

    services: MappingProxyType[str, Service] = field(init=False)
    """Application services registry."""

    _service_loading_order: list[Service] = field(init=False, default_factory=list)
    """List of services in order they must be initialized."""

    _service_map: dict[str, Service] = field(init=False, default_factory=dict)
    """Mutable mapping of all application services on their names."""

    _post_init_task: asyncio.Future | None = field(init=False, default=None)

    def __post_init__(self):
        """Initialize."""
        self.services = MappingProxyType(self._service_map)
        self.namespace = Namespace(self.env, self.name)

    def add_services(self, *services: Service) -> None:
        """Add new services to the application.

        The loading order must be resolved.
        """
        for service_ in services:
            if service_.name in self._service_map:
                raise ValueError(f"Trying to register a service with the same name twice: {service_.name}.") from None
            self._service_loading_order.append(service_)
            self._service_map[service_.name] = service_

    def set_context_var(self, key: str, value: Any) -> None:
        """Set variable in the current async call context."""
        ctx = self.context.get()
        if ctx is None:
            self.context.set({"_vars": {key: value}})
        else:
            ctx["_vars"][key] = value

    def get_context_var(self, key: str) -> Any | None:
        """Get key from the current async call context or None if no key."""
        ctx = self.context.get()
        if ctx is not None and "_vars" in ctx:
            return ctx["_vars"].get(key)
        return None

    def json_repr(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "debug": self.debug,
            "metadata": self.metadata,
            "scheduler": self.scheduler.json_repr(),
            "services": [
                {
                    "cls": _service.__class__.__name__,
                    "data": {"name": _service.name, "state": _service.state.get().value, **_service.json_repr()},
                }
                for _service in self._service_loading_order
            ],
            "tasks": [
                {
                    "name": task.get_name(),
                    "is_done": bool(task.done()),
                    "is_cancelling": bool(task.cancelling()),
                    "is_cancelled": bool(task.cancelled()),
                }
                for task in asyncio.all_tasks()
            ],
        }

    async def inspect(self, services: list[str] | None = None) -> dict:
        """Inspect the app and get all services data and health."""
        app_data = self.json_repr()
        healthy = True
        for service_data in app_data["services"]:
            service_name = service_data["data"]["name"]
            if services and service_name not in services:
                continue
            _service = self.services[service_name]
            service_data["health"] = service_health = await _service.get_health()
            healthy = healthy and service_health["healthy"]
        app_data["health"] = Health(healthy=healthy, stats={}, errors=[])
        return app_data

    async def start(self) -> None:
        """Initialize all services and tasks."""
        self.logger.info("starting")
        if self.debug:
            self.logger.warning("running in debug mode")

        await self.server.start()

        for n, _service in enumerate(self._service_loading_order):
            try:
                await asyncio.wait_for(_service.start(), self.service_start_timeout_s)
            except asyncio.TimeoutError:
                if _service.name not in self.optional_services:
                    await self.stop(n)
                    raise ServiceInitTimeout(
                        f"Service took too long to start: {_service.name}\n\n"
                        f"Fix: Optimize the service `init()` OR move time consuming code to service `post_init()` "
                        f"OR increase `app.settings.service_start_timeout_s` in project config file."
                    ) from None

                self.logger.error("Service took too long to start.", service=_service.name)
            except Exception as exc:
                if _service.name not in self.optional_services:
                    await self.stop(n)
                    raise ServiceInitFailed("Service failed on start.", service=_service.name) from exc
                self.logger.error("service failed on start", exc_info=exc, service=_service.name)

        await self.scheduler.start()
        self._post_init_task = asyncio.ensure_future(
            asyncio.gather(*(self._post_init_service(_service) for _service in self._service_loading_order))
        )
        if self.show_inspection_on_start or self.debug:
            inspect_data = await self.inspect()
            self.logger.info("inspection data", data=inspect_data)
        self.logger.debug("started")

    async def stop(self, _idx: int | None = None, /) -> None:
        """Stop all services and tasks."""
        self.logger.debug("stopping")
        await self.scheduler.stop()
        if _idx is None:
            _idx = len(self._service_loading_order)
        if self._post_init_task and not self._post_init_task.done():
            self._post_init_task.cancel()
        await asyncio.gather(
            *(self._close_service(_service) for _service in reversed(self._service_loading_order[:_idx])),
            return_exceptions=True,
        )
        if self._post_init_task and not self._post_init_task.done():
            with suppress(asyncio.CancelledError):
                await self._post_init_task
        self._post_init_task = None
        await self.server.stop()
        self.logger.info("stopped")

    async def _post_init_service(self, _service: Service, /) -> None:
        try:
            async with timeout(self.post_init_timeout_s):
                await _service.post_init()
        except asyncio.TimeoutError:
            self.logger.error("service post-init timeout", service=_service.name, max_timeout=self.post_init_timeout_s)
        except Exception as exc:
            self.logger.error("service post-init failed", exc_info=exc, service=_service.name)

    async def _close_service(self, _service: Service, /) -> None:
        try:
            async with timeout(self.service_start_timeout_s):
                await _service.stop()
        except asyncio.TimeoutError:
            self.logger.error("service stop timeout", service=_service.name, max_timeout=self.service_start_timeout_s)
        except Exception as exc:
            self.logger.error("service stop failed", exc_info=exc, service=_service.name)

    async def __aenter__(self) -> Self:
        """Enter service start/stop context."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit service start/stop context."""
        await self.stop()

    async def wait(self, _for_status: ServiceState = ServiceState.READY, /) -> None:
        """Wait until the service is ready."""
        await self.state.wait(_for_status)


def run_app(app: Application, /, loop: asyncio.AbstractEventLoop | None = None) -> None:
    if not loop:
        loop = asyncio.new_event_loop()
    if app.debug:
        loop.set_debug(True)
    try:
        loop.run_until_complete(app.start())
        loop.run_forever()
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        loop.run_until_complete(app.stop())
        tasks = asyncio.all_tasks(loop)
        if tasks:
            loop.run_until_complete(asyncio.wait(tasks))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
