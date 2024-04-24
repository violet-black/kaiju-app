"""Base and basic types."""

from abc import ABC
from typing import ClassVar, Mapping, TypedDict, Any

__all__ = ["Error", "ErrorData"]


class _ErrorDataData(TypedDict):
    type: str
    type_base: str
    extra: Mapping[str, Any]


class ErrorData(TypedDict):
    code: int
    message: str
    data: _ErrorDataData


class Error(BaseException, ABC):
    """Base error class for application errors.

    To get a JSONRPC compatible error user `json_repr` method:

    >>> Error('some error', value=1).json_repr()
    {'code': 0, 'message': 'some error', 'data': {'type': 'Error', 'type_base': 'BaseException', 'extra': {'value': 1}}}

    To wrap a standard exception in error type:

    >>> Error.wrap_exception(ValueError('something happened'))
    Error('something happened')

    """

    code: ClassVar[int] = 0
    """Error JSONRPC code"""

    def __init__(self, msg: str, /, **extra):
        BaseException.__init__(self, msg)
        self.extra = extra

    def json_repr(self):
        """JSONRPC compatible error data."""
        data = _ErrorDataData(
            type=self.__class__.__name__,
            type_base=self.__class__.__base__.__name__,
            extra=self.extra,
        )
        return ErrorData(code=self.code, message=self.args[0], data=data)

    @classmethod
    def wrap_exception(cls, exc: BaseException, /) -> "Error":
        if isinstance(exc, Error):
            return exc
        return cls(str(exc), from_=type(exc).__name__)
