from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class Cache(ABC):

    def __init__(self, size: int):
        if size <= 0:
            raise ValueError("Cache size must be a positive integer")
        self.size = size

    @abstractmethod
    def access(self, page_id: int) -> bool:
        """Access a page; return True on hit and False on miss."""

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """Return internal statistics (e.g., hit/miss counts)."""


