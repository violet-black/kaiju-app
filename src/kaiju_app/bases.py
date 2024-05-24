"""Base types and interfaces."""

from abc import abstractmethod
from typing import Any, Protocol

__all__ = ["JSONType", "Logger"]


class JSONType(Protocol):
    """JSON serializable type."""

    @abstractmethod
    def json_repr(self) -> dict[str, Any]: ...


class Logger(Protocol):
    """Logger interface."""

    @abstractmethod
    def critical(self, msg: str, /, *args, exc_info: BaseException | None = None, **kwargs) -> None: ...

    @abstractmethod
    def error(self, msg: str, /, *args, exc_info: BaseException | None = None, **kwargs) -> None: ...

    @abstractmethod
    def warning(self, msg: str, /, *args, exc_info: BaseException | None = None, **kwargs) -> None: ...

    @abstractmethod
    def info(self, msg: str, /, *args, exc_info: BaseException | None = None, **kwargs) -> None: ...

    @abstractmethod
    def debug(self, msg: str, /, *args, exc_info: BaseException | None = None, **kwargs) -> None: ...
