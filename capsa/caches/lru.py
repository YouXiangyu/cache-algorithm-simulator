from __future__ import annotations

from collections import OrderedDict
from typing import Dict

from ..cache_base import Cache


class LRUCache(Cache):
    """经典 LRU 缓存，基于 OrderedDict 实现 O(1) 操作。"""

    def __init__(self, size: int):
        super().__init__(size)
        self.data: "OrderedDict[int, None]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def access(self, page_id: int) -> bool:
        hit = page_id in self.data
        if hit:
            self.data.move_to_end(page_id, last=True)
            self.hits += 1
        else:
            self.misses += 1
            if len(self.data) >= self.size:
                self.data.popitem(last=False)
            self.data[page_id] = None
        return hit

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses}


