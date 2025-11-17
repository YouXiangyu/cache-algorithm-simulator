from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class Cache(ABC):
    """抽象缓存接口，所有缓存算法都必须实现。"""

    def __init__(self, size: int):
        if size <= 0:
            raise ValueError("缓存容量必须为正整数")
        self.size = size

    @abstractmethod
    def access(self, page_id: int) -> bool:
        """访问一个页面，命中返回 True，未命中返回 False。"""

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """返回内部统计信息，例如命中/未命中次数。"""


