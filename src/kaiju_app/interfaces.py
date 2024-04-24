"""Common interfaces and protocols."""

from typing import Protocol, Any

__all__ = ["JSONSerializable", "Contextable"]


class JSONSerializable(Protocol):

    def json_repr(self) -> dict[str, Any]: ...


class Contextable(Protocol):

    async def start(self) -> None: ...

    async def stop(self) -> None: ...
