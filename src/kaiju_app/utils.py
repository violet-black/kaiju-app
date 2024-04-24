"""Utility functions and classes."""

import asyncio
from abc import ABC
from ast import literal_eval
from bisect import bisect
from collections.abc import Hashable, Sized
from contextlib import suppress
from typing import Any, Collection, Generic, Iterable, Mapping, TypeVar, NewType

from kaiju_scheduler import RetryError, retry, timeout
from template_dict import Template

__all__ = [
    "timeout",
    "eval_string",
    "RetryError",
    "retry",
    "State",
    "SortedStack",
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
    """Namespace object to manage string suffixes and prefixes.

    Create a namespace:

    >>> Namespace('dev')
    Namespace('_dev')

    >>> Namespace('dev', 'app')
    Namespace('_dev._app')

    Check if namespaces are the same:

    >>> Namespace('dev') == Namespace('_dev')
    True

    Get a key:

    >>> Namespace('dev').get('key')
    '_dev.key'

    Alternatively:

    >>> Namespace('dev')['key']
    '_dev.key'

    Check if a key matches the namespace:

    >>> '_dev.key' in Namespace('dev')
    True

    Get a sub-namespace:

    >>> Namespace('dev', 'app').get_child('cache')
    Namespace('_dev._app._cache')

    You can use namespace as keys:

    >>> {Namespace('dev'): [], Namespace('prod'): []}
    {Namespace('_dev'): [], Namespace('_prod'): []}

    """

    namespace_prefix = "_"
    """Namespace prefix is used before each namespace name, it distinguish namespaces from keys."""

    delimiter = "."
    """Delimiter between a namespace and a sub-namespace or a key."""

    __slots__ = ("_name",)

    def __init__(self, *name: str):
        _name = []
        for name_part in name:
            if name_part.startswith(self.namespace_prefix):
                name_part = name_part.lstrip(self.namespace_prefix)
            if self.delimiter in name_part:
                raise ValueError(f'Name must not contain a delimiter symbol "{self.delimiter}", got "{name_part}"')
            _name.append(f"{self.namespace_prefix}{name_part}")
        self._name = self.delimiter.join(_name)

    def get_child(self, suffix: str, /) -> "Namespace":
        """Get sub-namespace from the current one."""
        return Namespace(*self._name.split("."), suffix)

    def get(self, key: str, /) -> NSKey:
        """Get a key what belongs to this namespace."""
        if self.delimiter in key:
            raise ValueError(f'Key must not contain a delimiter symbol "{self.delimiter}"')
        if key.startswith(self.namespace_prefix):
            raise ValueError(f'Key must not start with a namespace prefix "{self.namespace_prefix}"')
        return NSKey(self.delimiter.join((self._name, key)))

    def __getitem__(self, key: str, /) -> NSKey:
        return self.get(key)

    def __contains__(self, key: NSKey | str, /) -> bool:
        """Check if a key belongs to the namespace."""
        return key.startswith(self._name)

    def __eq__(self, other):
        return isinstance(other, Namespace) and str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self._name)

    def __repr__(self):
        return f"Namespace('{self._name}')"

    def __str__(self):
        return self._name


class State(Generic[_Status], ABC):
    """Awaitable state machine.

    To create you state machine you must create a status list and assign it to your subclass.

    >>> from enum import Enum
    ...
    >>> class UserStatus(Enum):
    ...     # it's recommended to use the same values for both name and a value
    ...     INACTIVE = 'INACTIVE'
    ...     ACTIVE = 'ACTIVE'
    ...     BANNED = 'BANNED'

    Now you can create and maintain the state of your object. Note that by default it uses the first status from the
    enum unless `state` parameter is explicitly provided.
    You can get the current state using :py:meth:`~kaiju_base.helpers.State.get` method.

    >>> class User:
    ...     def __init__(self):
    ...         self.state = State(UserStatus, UserStatus.INACTIVE)
    ...
    >>> user = User()
    >>> user.state.get().name
    'INACTIVE'

    >>> str(user.state)
    'INACTIVE'

    You can set the state using :py:meth:`~kaiju_base.helpers.State.set` method.

    >>> user.state.set(UserStatus.ACTIVE)

    It's also possible to use the state change contextto change an object state inside a function.

    >>> with user.state:
    ...     user.state.set(UserStatus.BANNED)
    ...     user.state.set(UserStatus.INACTIVE)
    ...     raise ValueError('Unhandled error')
    Traceback (most recent call last):
    ...
    ValueError: Unhandled error

    In any error the last state before context is preserved.

    >>> user.state.get().name
    'ACTIVE'

    Two object states can be compared.

    >>> other_user = User()
    >>> other_user.state.set(UserStatus.ACTIVE)
    >>> other_user.state == user.state
    True

    You can also check if the state object has a particular inner state by calling this method.

    >>> other_user.state.is_(UserStatus.ACTIVE)
    True

    Of course, a state machine would be useless in the async context if there would be no way to wait
    for a particular state. You can use :py:meth:`~kaiju_base.helpers.State.wait` to wait for a particular state.

    >>> async def wait_banned(_user: User):
    ...  await _user.state.wait(UserStatus.BANNED)
    ...  return 'Banned!'

    Test example:

    >>> async def ban_user(_user: User):
    ...     _user.state.set(UserStatus.BANNED)

    >>> async def _main():
    ...     return await asyncio.gather(wait_banned(user), ban_user(user))

    >>> asyncio.run(_main())
    ['Banned!', None]

    """

    __slots__ = ("_events", "_status", "_fallback_status")

    def __init__(self, status_list: Collection[_Status], status: _Status):
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
        self._events[state].set()
        self._status = state

    async def wait(self, state: _Status, /) -> None:
        await self._events[state].wait()

    def __enter__(self):
        self._fallback_status = self._status
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.set(self._fallback_status)

    def __eq__(self, other, /) -> bool:
        if not isinstance(other, State):
            return False
        return self.get() is other.get()

    def __hash__(self, /) -> int:
        return hash(self.get())

    def __str__(self):
        return str(self._status.value)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {repr(self._status)}>"


class SortedStack(Sized, Iterable, Generic[_Item]):
    """Sorted stack of elements.

    >>> stack = SortedStack({'dogs': 12, 'sobaki': 5})
    >>> stack = SortedStack(stack)
    >>> stack.add(*SortedStack({'cats': 5}))

    Selection:

    >>> stack.select(8)
    ['sobaki', 'cats']

    >>> stack.rselect(8)
    ['dogs']

    Insertion and removal:

    >>> stack.add(('koty', 1))
    >>> stack.pop_many(3)
    ['koty']

    >>> stack.pop()
    'sobaki'

    >>> len(stack)
    2

    >>> stack.clear()
    >>> bool(stack)
    False

    """

    __slots__ = ("_scores", "_values")

    def __init__(self, items: Iterable[tuple[_Item, Any]] | dict[_Item, Any], /):
        """Initialize."""
        self._scores: list[Any] = []
        self._values: list[_Item] = []
        if items:
            if isinstance(items, dict):
                items = items.items()
            self.add(*items)

    @property
    def lowest_score(self) -> Any | None:
        """Get the lowest score in the stack."""
        return next(iter(self._scores), None)

    def add(self, *items: tuple[_Item, Any]):
        """Extend the stack by adding more than one element."""
        for item, score in items:
            idx = bisect(self._scores, score)
            self._scores.insert(idx, score)
            self._values.insert(idx, item)

    def select(self, score_threshold, /) -> list[_Item]:
        """Select and return items without removing them from the lowest score to `score_threshold`.

        The values are guaranteed to be in order.
        """
        return self._select(score_threshold, reverse=False)

    def rselect(self, score_threshold: Any, /) -> list[_Item]:
        """Select and return items without removing them from the highest score to `score_threshold`.

        The values are guaranteed to be in order.
        """
        return self._select(score_threshold, reverse=True)

    def pop(self) -> _Item:
        """Pop a single element which has the lowest score.

        :raises StopIteration: if there are no values to return.
        """
        return self._pop(reverse=False)

    def rpop(self) -> _Item:
        """Pop a single element which has the highest score.

        :raises StopIteration: if there are no values to return.
        """
        return self._pop(reverse=True)

    def pop_many(self, score_threshold: Any, /) -> list[_Item]:
        """Pop and return values with scores less than `score_threshold`.

        The returned values are guaranteed to be in order.
        Returns an empty list if no values.
        """
        return self._pop_many(score_threshold, reverse=False)

    def rpop_many(self, score_threshold: Any, /) -> list[_Item]:
        """Pop and return values with scores greater than `score_threshold`.

        Returned values are guaranteed to be in order.
        """
        return self._pop_many(score_threshold, reverse=True)

    def clear(self) -> None:
        """Clear all values."""
        self._scores.clear()
        self._values.clear()

    def __iter__(self):
        return iter(zip(self._values, self._scores))

    def __len__(self):
        return len(self._values)

    def _pop_many(self, score_threshold: Any, reverse: bool = False) -> list[_Item]:
        """Pop values with scores less than `score`.

        The returned values are guaranteed to be in order.
        Returns an empty list if no values.
        """
        idx = bisect(self._scores, score_threshold)
        if reverse:
            self._scores = self._scores[:idx]
            values, self._values = self._values[idx:], self._values[:idx]
        else:
            self._scores = self._scores[idx:]
            values, self._values = self._values[:idx], self._values[idx:]
        return values

    def _pop(self, reverse: bool = False) -> _Item:
        if not self._values:
            raise StopIteration("Empty stack.")
        if reverse:
            del self._scores[-1]
            return self._values.pop(-1)
        else:
            del self._scores[0]
            return self._values.pop(0)

    def _select(self, score_threshold: Any, reverse: bool = False) -> list[_Item]:
        """Select and return items without removing them from the stack.

        The values are guaranteed to be in order.
        """
        idx = bisect(self._scores, score_threshold)
        if reverse:
            values = self._values[idx:]
            values.reverse()
            return values
        else:
            return self._values[:idx]
