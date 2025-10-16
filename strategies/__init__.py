"""Strategy utilities."""
from __future__ import annotations

import inspect
from importlib import import_module
from typing import Type

from .base_strategy import BaseStrategy


def load_strategy(name: str) -> BaseStrategy:
    module = import_module(f"strategies.{name}")
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if inspect.isclass(attr) and issubclass(attr, BaseStrategy) and attr is not BaseStrategy:
            return attr()
    raise ValueError(f"No strategy class found in strategies.{name}")
