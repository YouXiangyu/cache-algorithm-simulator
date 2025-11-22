from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class Cache(ABC):
    """抽象缓存接口，所有缓存算法必须实现此接口。"""

    def __init__(self, size: int):
        if size <= 0:
            raise ValueError("Cache size must be a positive integer")
        self.size = size

    @abstractmethod
    def access(self, page_id: int) -> bool:
        """访问一个页面，命中返回True，未命中返回False。"""

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """返回内部统计信息，例如命中/未命中计数。"""


