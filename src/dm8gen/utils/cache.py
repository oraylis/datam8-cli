"""
Simple caching module to use during template rendering when generating or
creating values, by using the following classes.

* Cache
* CacheEntry
"""

from dataclasses import dataclass
from typing import Any, Type


@dataclass
class CacheEntry:
    type: Type
    value: Any


class Cache:
    __dict: dict[str, CacheEntry]

    def __init__(self):
        self.__dict = {}

    def get(self, key: str) -> Any:
        """Get a value from the cache by key.

        Args
            key (str): identifier to retrieve the value for.

        Returns
        ---------------
        The value matching the given key.
        """
        return self.__dict[key].value

    def set(self, key: str, value: object) -> object:
        """Set the value in cache by key and return it.

        Args
            key (str): identifier to set the value.
            value (object): value to set.

        Returns
        -------------
        The newly set value.
        """
        self.__dict[key] = CacheEntry(type=type(value), value=value)
        return value

    @property
    def all(self) -> dict[str, CacheEntry]:
        """Return the complete cache dictionary."""
        return self.__dict

    @property
    def items(self) -> dict[str, Any]:
        """Return all key-value pairs currently in the cache."""
        return {k: v.value for k, v in self.__dict.items()}

    def __str__(self):
        return "Cached Items: " + ", ".join(
            ["%s(%s)" % (k, str(v.value)) for k, v in self.__dict.items()]
        )
