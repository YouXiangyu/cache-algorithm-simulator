from __future__ import annotations

from collections import OrderedDict
from typing import Dict

from ..cache_base import Cache


class ARCCache(Cache):
    """自适应替换缓存 ARC，实现 Figure 4 伪代码逻辑。"""

    def __init__(self, size: int):
        super().__init__(size)
        self.T1: "OrderedDict[int, None]" = OrderedDict()  # 使用Ordered dict来实现LRU队列
        self.T2: "OrderedDict[int, None]" = OrderedDict()
        self.B1: "OrderedDict[int, None]" = OrderedDict()
        self.B2: "OrderedDict[int, None]" = OrderedDict()
        self.p = 0
        self.hits = 0
        self.misses = 0

    def _move_to_T2(self, page_id: int) -> None:
        self.T2[page_id] = None

    def _replace(self, page_id: int) -> None:
        if self.T1 and (
            len(self.T1) > self.p or (page_id in self.B2 and len(self.T1) == self.p)
        ):
            old, _ = self.T1.popitem(last=False)
            self.B1[old] = None
            if len(self.B1) > self.size:
                self.B1.popitem(last=False)
        else:
            if self.T2:
                old, _ = self.T2.popitem(last=False)
                self.B2[old] = None
                if len(self.B2) > self.size:
                    self.B2.popitem(last=False)

    def _adapt_p_on_b1_hit(self) -> None:
        if self.B1:
            delta = max(1, len(self.B2) // len(self.B1))
        else:
            delta = 1
        self.p = min(self.size, self.p + delta)

    def _adapt_p_on_b2_hit(self) -> None:
        if self.B2:
            delta = max(1, len(self.B1) // len(self.B2))
        else:
            delta = 1
        self.p = max(0, self.p - delta)

    def _ensure_space_for_miss(self) -> None:
        total = len(self.T1) + len(self.B1)
        if total == self.size:
            if len(self.T1) < self.size:
                self.B1.popitem(last=False)
                self._replace(None)
            else:
                old, _ = self.T1.popitem(last=False) #表示弹出“最早的项”
                # self.B1[old] = None
        else:
            grand_total = total + len(self.T2) + len(self.B2)
            if grand_total >= self.size:
                if grand_total == 2 * self.size and self.B2:
                    self.B2.popitem(last=False)
                self._replace(None)

# 应该没有问题
    def access(self, page_id: int) -> bool:
        if page_id in self.T1:
            self.T1.pop(page_id, None)
            self._move_to_T2(page_id)
            self.hits += 1
            return True

        if page_id in self.T2:
            self.T2.pop(page_id, None)
            self._move_to_T2(page_id)
            self.hits += 1
            return True

        self.misses += 1

        if page_id in self.B1:
            self._adapt_p_on_b1_hit()
            self._replace(page_id)
            self.B1.pop(page_id, None)
            self._move_to_T2(page_id)
            return False

        if page_id in self.B2:
            self._adapt_p_on_b2_hit()
            self._replace(page_id)
            self.B2.pop(page_id, None)
            self._move_to_T2(page_id)
            return False

        self._ensure_space_for_miss()
        self.T1[page_id] = None
        return False

    def get_stats(self) -> Dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "p": int(self.p)}


