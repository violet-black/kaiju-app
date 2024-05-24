"""Error types specification."""

import asyncio
from abc import ABC
from inspect import isclass
from typing import Mapping, TypedDict, NotRequired, Any, ClassVar, TypeVar

__all__ = [
    "Error",
    "ErrorData",
    "ERRORS",
    "create_error",
    "wrap_exception",
    "DataError",
    "ServerError",
    "PermissionError",
    "NotFound",
    "Conflict",
    "DataTooLarge",
    "ValidationError",
    "InternalError",
    "Timeout",
    "Cancelled",
    "ServiceNotAvailable",
    "AuthorizationFailed",
    "AuthorizationExpired",
    "Unauthorized",
    "PermissionDenied",
    "InvalidRequest",
    "InvalidParams",
    "MethodNotFound",
    "InvalidParams",
    "ParseError",
]


class _ErrorBaseData(TypedDict):
    code: int  #: error code
    type: str  #: error type name


class _ErrorDataData(TypedDict):
    code: int  #: error code
    type: str  #: error type name
    base: _ErrorBaseData  #: error base type
    extra: NotRequired[Mapping[str, Any]]  #: additional info


class ErrorData(TypedDict):
    """Universal error data format compatible with JSONRPC protocol."""

    code: int  #: unique integer error code
    message: str  #: human-readable message
    data: _ErrorDataData  #: error attributes


class Error(Exception, ABC):
    """A base class for all RPC compatible error types.

    The error format is itself compatible with JSONRPC 2.0 specification
    and can be serialized into a JSON structure, which contains error code and type, error message and all extra data.

    >>> error = Timeout('Request timed out', timeout_s=60, request_id='ffffff')
    >>> error_data = error.json_repr()

    .. code-block:: json

        {
            "code": -32002,
            "message": "Request timed out",
            "data": {
                "code": -32002,
                "type": "Timeout",
                "base": {
                    "code": -32000,
                    "type": "ServerError"
                },
                "extra": {
                    "timeout_s": 60,
                    "request_id": "ffffff"
                }
            }
        }

    An error can be created back from its error data. If there's no such error code in the error types map
    then the 'base' error type will be used.

    >>> create_error(error_data)
    Timeout('Request timed out')

    To create your error type you should inherit it from the base error type or from one of the standard types and
    assing an error code to it. See the base error types and their codes below.

    .. code-block:: python

        from kaiju_app.errors import DataError, ERRORS

        class FileNotFound(DataError):
            code = -31749

        ERRORS[FileNotFound.code] = FileNotFound

    You can now serialize this error type and deserialize it using :py:func:`~kaiju_app.errors.create_error` on
    receiving a JSONRPC error response.

    .. code-block:: python

        from kaiju_app.errors import create_error

        data = json.loads(body)
        if 'error' in data:
            error = create_error(data['error'])

    """

    code: ClassVar[int] = -1

    def __init__(self, msg: str, /, **extra):
        Exception.__init__(self, msg)
        self.extra = extra

    def json_repr(self) -> ErrorData:
        """JSONRPC compatible error data."""
        data = _ErrorDataData(
            code=self.code,
            type=self.__class__.__name__,
            base=_ErrorBaseData(
                code=getattr(self.__class__.__base__, "code", -1),
                type=self.__class__.__base__.__name__,
            ),
        )
        if self.extra:
            data["extra"] = self.extra
        return ErrorData(code=self.code, message=self.args[0], data=data)


class DataError(Error):
    """Error during data manipulation on a server.

    **Range:** -31744 to -31999 (-0x7c00 to -0x7cff)

    Data errors are related to data sent to and from the server and processed by server methods. It includes database
    interaction, file management, etc.

    .. code-block::

        -31745  NotFound
        -31746  Conflict
        -31747  DataTooLarge
        -31748  ValidationError
        ...
        -31801 .. -31999  user-defined errors

    """

    code = -31744


class NotFound(DataError):
    code = -31745


class Conflict(DataError):
    code = -31746


class DataTooLarge(DataError):
    code = -31747


class ValidationError(DataError):
    code = -31748


class ServerError(Error):
    """Error occurred during a request execution on a server.

    **Range:** -32000 to -32255 (-0x7d00 to -0x7dff)

    Server errors are reserved for RPC server execution of the request. It may be due to the server terminating the request
    due to some internal problem or internal instructions or because a service is unavailable. Generally there's no way
    for a client to prevent such type of error which distinguishes server errors from client errors.

    .. code-block::

        -32001  InternalError
        -32002  Timeout
        -32003  Cancelled
        -32004  ServiceNotAvailable
        ...
        -32101 .. -32255  user-defined errors

    """

    code = -32000


class InternalError(ServerError):
    code = -32001


class Timeout(ServerError, asyncio.TimeoutError):
    code = -32002


class Cancelled(ServerError, asyncio.CancelledError):
    code = -32003


class ServiceNotAvailable(ServerError):
    code = -32004


class PermissionError(Error):
    """Error due to permission or authorization failure.

    **Range:** -32256 to -32511 (-0x7e00 to -0x7eff)

    Permission error should be generated when there's a problem with credentials or permission of the particular request.
    It should be generated by the authentication / permission backend before the request is sent to the server. The
    permission error is then returned immediately to the client. However there could be certain cases when it may be
    returned during the execution of the request.

    .. code-block::

        -32257  AuthorizationFailed
        -32258  AuthorizationExpired
        -32259  Unauthorized
        -32260  PermissionDenied
        ...
        -32301 .. -32511  user-defined errors

    """

    code = -32256


class AuthorizationFailed(PermissionError):
    code = -32257


class AuthorizationExpired(PermissionError):
    code = -32258


class Unauthorized(PermissionError):
    code = -32259


class PermissionDenied(PermissionError):
    code = -32260


class ClientError(Error):
    """Invalid client input error.

    **Range:** -32512 to -32767 (-0x7f00 to -0x7fff)

    Client RPC error should be generated upon validating an incoming request before it has been sent
    to the server for the execution. The client error is then returned immediately to the client.

    .. code-block::

        -32600  InvalidRequest
        -32601  MethodNotFound
        -32602  InvalidParams
        -32603  (used for internal error in the original JSONRPC spec - bad)
        -32700  ParseError
        ...
        -32701 .. -32767  user-defined errors

    """

    code = -32512


class InvalidRequest(ClientError):
    code = -32600


class MethodNotFound(ClientError):
    code = -32601


class InvalidParams(ClientError):
    code = -32602


class ParseError(ClientError):
    code = -32700


ERRORS: dict[int, type[Error]] = {}  #: global registry of common error types

for value in list(globals().values()):
    if isclass(value) and issubclass(value, Error):
        ERRORS[value.code] = value


def create_error(data: ErrorData, error_types: Mapping[int, type[Error]] = None) -> Error:
    """Create an error object from error data."""
    if error_types is None:
        error_types = ERRORS
    code = data["code"]
    message = data["message"]
    extra = data["data"].get("extra", {})
    if code in error_types:
        return error_types[code](message, **extra)
    code = data["data"]["base"]["code"]
    if code in error_types:
        return error_types[code](message, **extra)
    return Error(message, **extra)


_Error = TypeVar("_Error", bound=Error)


def wrap_exception(exc: Exception, error_type: type[_Error] = Error) -> _Error:
    """Convert a Python exception to an RPC compatible error."""
    return error_type(str(exc), from_=exc.__class__.__name__)
