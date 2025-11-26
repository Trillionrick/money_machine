"""Shared type definitions using Python 3.12+ modern syntax."""

from collections.abc import Mapping
from typing import Any

# Type aliases using PEP 695 syntax
type ContextMap = Mapping[str, Any]
type Symbol = str
type Price = float
type Quantity = float
type Timestamp = int  # nanosecond epoch
