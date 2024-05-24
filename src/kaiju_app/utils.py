"""Utility functions and classes."""

import asyncio
import re
from ast import literal_eval
from collections.abc import Hashable
from contextlib import suppress
from types import MappingProxyType
from typing import Any, Iterable, Generic, Mapping, NewType, TypeVar, Self, Callable, Awaitable

from template_dict import Template

from kaiju_app.bases import Logger

__all__ = [
    "timeout",
    "eval_string",
    "RetryError",
    "retry",
    "State",
    "Template",
    "merge_dicts",
    "Namespace",
]

_Status = TypeVar("_Status", bound=Hashable)
_Item = TypeVar("_Item", bound=Hashable)
_env_vars_defaults = {"true": True, "false": False, "none": None, "null": None}
NSKey = NewType("NSKey", str)  #: namespace compatible key


def merge_dicts(*dicts: Mapping) -> dict:
    """Merge multiple dicts into a new one recursively.

    The function is optimized for simple JSON compatible data types. It may not work as expected for some custom
    collections. See the sources and decide for yourself.

    The priority is from first to last, the last dict overwrites the first.

    >>> merge_dicts({"a": 1, "b": 2}, {"a": 3, "c": 4})
    {'a': 3, 'b': 2, 'c': 4}

    Note that mutable collections will be merged (lists, sets, dicts).

    >>> merge_dicts({"a": [1, 2], "b": {1}, "c": {"d": 1}}, {"a": [3], "b": {2}, "c": {"e": 2}})
    {'a': [1, 2, 3], 'b': {1, 2}, 'c': {'d': 1, 'e': 2}}

    Immutable collections are treated as frozen values and can only be replaced.

    >>> merge_dicts({"a": (1, 2), "b": frozenset({5})}, {"a": (3, 4), "b": frozenset({6})})
    {'a': (3, 4), 'b': frozenset({6})}
    """
    merged_dict = {}
    for _dict in dicts:
        for key, value in _dict.items():
            if key not in merged_dict:
                merged_dict[key] = value
                continue
            if isinstance(value, dict):
                merged_dict[key] = merge_dicts(merged_dict[key], value)
            elif isinstance(value, list):
                merged_dict[key] = [*merged_dict[key], *value]
            elif isinstance(value, set):
                merged_dict[key] = merged_dict[key].union(value)
            else:
                merged_dict[key] = value
    return merged_dict


def eval_string(value: str, /) -> Any:
    """Evaluate an environment text value into a python variable using save eval.

    This method is useful when loading values from Unix environment or CLI arguments.

    There are few predefined values: `true, false, none, null` will be evaluated to `True`, `False` and `None` with
    disregard of their case.

    >>> eval_string('true')
    True

    Empty values are evaluated to `None`.

    >>> eval_string('')

    In all other cases a value will be evaluated with python `eval()` function.

    >>> eval_string('[1, 2, 3]')
    [1, 2, 3]

    >>> eval_string('"42"')
    '42'

    """
    value = value.strip()
    if not value:
        return None
    _lcase = value.lower()
    if _lcase in _env_vars_defaults:
        return _env_vars_defaults[_lcase]
    with suppress(Exception):
        return literal_eval(value)
    return value


class Namespace:
    """Namespace object allows consistently concatenate name parts.

    Keys and other namespaces may be derived from namespaces, which allows one to organize keys and prevent
    key collisions. Use namespaces when creating cache keys, topic names, etc.

    Specification
    =============

    - Symbols in keys and namespace names MUST be one of: [0-9a-z_-]
    - Namespaces and subnamespaces MUST be prefixed with _ (underscore)
    - Keys MUST NOT be prefixed with _ (underscore)
    - Name parts MUST be split by . (dot)

    Examples
    ========

    Example of a namespace:

    '_dev._my_app._cache'

    Example of a key:

    '_dev._my_app._cache.some_key'

    Create a namespace:

    >>> Namespace('dev')
    <Namespace('_dev')>

    >>> Namespace('dev', 'app')
    <Namespace('_dev._app')>

    Check if namespaces are the same:

    >>> Namespace('dev') == Namespace('_dev')
    True

    Get a key:

    >>> Namespace('dev').get('key')
    '_dev.key'

    Check if a key matches the namespace:

    >>> '_dev.key' in Namespace('dev')
    True

    Get a sub-namespace:

    >>> Namespace('dev', 'app').get_child('cache')
    <Namespace('_dev._app._cache')>

    You can use namespace as map keys:

    >>> {Namespace('dev'): [], Namespace('prod'): []}
    {<Namespace('_dev')>: [], <Namespace('_prod')>: []}

    """

    __slots__ = ("_name",)

    _invalid_chars = re.compile(r"[^a-z0-9_-]")

    def __init__(self, *name: str):
        _name = []
        for name_part in name:
            if name_part.startswith("_"):
                name_part = name_part.lstrip("_")
            if self._invalid_chars.search(name_part):
                raise ValueError("Namespace name must contain one of: a-z, 0-9, - or _")
            _name.append(f"_{name_part}")
        self._name = ".".join(_name)

    def get_child(self, suffix: str, /) -> "Namespace":
        """Get sub-namespace from the current one."""
        return Namespace(*self._name.split("."), suffix)

    def get(self, key: str, /) -> NSKey:
        """Get a key what belongs to this namespace."""
        if key.startswith("_"):
            raise ValueError(f"Namespace key must not start with an underscore")
        if self._invalid_chars.search(key):
            raise ValueError(f"Namespace key must contain one of: a-z, 0-9, - or _")
        return NSKey(".".join((self._name, key)))

    def __contains__(self, key: NSKey | str, /) -> bool:
        """Check if a key belongs to the namespace."""
        return key.startswith(self._name)

    def __eq__(self, other, /) -> bool:
        return isinstance(other, Namespace) and str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self._name)

    def __repr__(self) -> str:
        return f"<Namespace('{self._name}')>"

    def __str__(self) -> str:
        return self._name


class State(Generic[_Status]):
    """State machine.

    The state object allows one to manage object state and also asynchronously wait for a specific state.

    To create you state object you must create a status list and assign it to your subclass. State values themselves
    must be hashable.

    >>> from enum import Enum
    ...
    >>> class UserStatus(Enum):
    ...     # it's recommended to use the same values for both name and a value
    ...     INACTIVE = 'INACTIVE'
    ...     ACTIVE = 'ACTIVE'
    ...     BANNED = 'BANNED'

    Now you can create and maintain the state of your object by passing an iterable of all status types and the current
    status.

    >>> class User:
    ...     def __init__(self):
    ...         self.state = State(UserStatus, UserStatus.INACTIVE)
    ...
    >>> user = User()
    >>> user.state.get().name
    'INACTIVE'

    >>> str(user.state)
    'UserStatus.INACTIVE'

    Set the state:

    >>> user.state.set(UserStatus.ACTIVE)

    You can manage state inside the state object context. This ensures that if an error happens then the state will be
    reverted to the one prior to entering the context.

    >>> with user.state:
    ...     user.state.set(UserStatus.BANNED)
    ...     user.state.set(UserStatus.INACTIVE)
    ...     raise ValueError('Unhandled error')
    Traceback (most recent call last):
    ...
    ValueError: Unhandled error

    As you can see the state was reverted to 'ACTIVE' due to an error:

    >>> user.state.get().name
    'ACTIVE'

    Two object states can be compared.

    >>> other_user = User()
    >>> other_user.state.set(UserStatus.ACTIVE)
    >>> other_user.state == user.state
    True

    You can also check the inner status directly:

    >>> other_user.state.is_(UserStatus.ACTIVE)
    True

    There's a way to continue only if a particular state has been reached by waiting for it asynchronously.

    >>> async def wait_banned(_user: User):
    ...  await _user.state.wait(UserStatus.BANNED)
    ...  return 'Banned!'
    ...
    >>> async def ban_user(_user: User):
    ...     _user.state.set(UserStatus.BANNED)
    ...
    >>> async def _main():
    ...     return await asyncio.gather(wait_banned(user), ban_user(user))
    ...
    >>> asyncio.run(_main())
    ['Banned!', None]

    """

    __slots__ = ("_events", "_status", "_fallback_status")

    def __init__(self, status_list: Iterable[_Status], status: _Status):
        """Initialize.

        :param status_list:
        :param status: initial status, the first value from `self.Status` is used by default
        """
        self._fallback_status: _Status = status
        self._status: _Status = status
        self._events: dict[_Status, asyncio.Event] = {_state: asyncio.Event() for _state in status_list}
        self.set(status)

    def get(self) -> _Status:
        return self._status

    def is_(self, state: _Status, /) -> bool:
        return self._status is state

    def set(self, state: _Status, /) -> None:
        for _state in self._events.values():
            _state.clear()
        if state not in self._events:
            raise ValueError(f'Unexpected state: "{state}"')
        self._events[state].set()
        self._status = state

    async def wait(self, state: _Status, /) -> None:
        if state not in self._events:
            raise ValueError(f'Unexpected state: "{state}"')
        await self._events[state].wait()

    def __enter__(self) -> Self:
        self._fallback_status = self._status
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.set(self._fallback_status)

    def __eq__(self, other, /) -> bool:
        if not isinstance(other, State):
            return False
        return self.get() is other.get()

    def __hash__(self, /) -> int:
        return hash(self.get())

    def __str__(self) -> str:
        return str(self._status)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({tuple(self._events.keys())}, {repr(self._status)}>)"


class RetryError(Exception):
    """Error recognized by :py:func:`~kaiju_scheduler.utils.retry` as suitable for retry."""


def timeout(time_sec: float, /):
    """Execute async callables within a timeout.

    .. code-block:: python

        async with timeout(5):
            await do_something_asynchronous()

    """
    return _Timeout(time_sec)


class _Timeout:
    __slots__ = ("_timeout", "_loop", "_task", "_handler")

    _handler: asyncio.Handle

    def __init__(self, time_sec: float, loop=None):
        self._timeout = max(0.0, time_sec)
        self._loop = loop
        # self._handler: asyncio.Task = None

    async def __aenter__(self):
        if self._loop is None:
            loop = asyncio.get_running_loop()
        else:
            loop = self._loop
        task = asyncio.current_task()
        self._handler = loop.call_at(loop.time() + self._timeout, self._cancel_task, task)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.CancelledError:
            raise asyncio.TimeoutError("Timeout")
        if self._handler:
            self._handler.cancel()

    @staticmethod
    def _cancel_task(task: asyncio.Task):
        task.cancel()


async def retry(
    func: Callable[..., Awaitable[Any]],
    retries: int,
    args: Iterable[Any] = tuple(),
    kws: Mapping[str, Any] = MappingProxyType({}),
    *,
    interval_s: float = 1.0,
    timeout_s: float = 120.0,
    catch_exceptions: tuple[type[BaseException], ...] = (TimeoutError, IOError, ConnectionError, RetryError),
    logger: Logger | None = None,
):
    """Retry function call

    :param func: async callable
    :param retries: number of retries
    :param args: positional arguments
    :param kws: keyword arguments
    :param interval_s: interval in seconds between retries
    :param timeout_s: total timeout in seconds for all retries
    :param catch_exceptions: catch certain exception types and retry when they happen
    :param logger: optional logger
    :return: returns the function result
    """
    async with timeout(timeout_s):
        while retries + 1 > 0:
            try:
                return await func(*args, **kws)
            except catch_exceptions as exc:
                retries -= 1
                if logger is not None:
                    logger.info("retrying on error", exc_info=exc)
                await asyncio.sleep(interval_s)
