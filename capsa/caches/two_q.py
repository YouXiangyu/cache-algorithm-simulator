from __future__ import annotations

from collections import OrderedDict
from typing import Dict

from ..cache_base import Cache


class TwoQCache(Cache):
    """2Q 双队列缓存策略，利用 FIFO 热身队列与 LRU 主队列结合降低缓存污染。"""

    def __init__(
        self,
        size: int,
        *,
        a1in_size: int | None = None,
        a1out_size: int | None = None,
    ):
        super().__init__(size)
        self.size = size
        default_in = int(size * 0.5)
        self.size_in = max(1, min(size - 1, a1in_size if a1in_size is not None else default_in))
        default_out = 16
        self.size_out = max(1, a1out_size if a1out_size is not None else default_out)
        self.size_am = max(1, size - self.size_in)
        self.A1in: "OrderedDict[int, None]" = OrderedDict()  # 仅访问过一次的页（FIFO）
        self.A1out: "OrderedDict[int, None]" = OrderedDict()  # 最近被淘汰的冷页面记录
        self.Am: "OrderedDict[int, None]" = OrderedDict()  # 访问至少两次的热页面（LRU）
        self.hits = 0
        self.misses = 0

    def _evict_from_a1in(self) -> None:
        if not self.A1in:
            return
        victim, _ = self.A1in.popitem(last=False)
        self.A1out[victim] = None
        if len(self.A1out) > self.size_out:
            self.A1out.popitem(last=False)

    def _evict_from_am(self) -> None:
        if self.Am:
            self.Am.popitem(last=False)
        #else:
           # self._evict_from_a1in()


    def access(self, page_id: int) -> bool:
        if page_id in self.Am:
            self.hits += 1
            self.Am.move_to_end(page_id)
            return True

        if page_id in self.A1in:
            # 第二次访问A1in中的页面，证明是热数据，移动到Am队列
            self.hits += 1
            return True

        self.misses += 1

        if page_id in self.A1out:
            # 命中 ghost，视为重用：腾挪空间并放入主队列
            if len(self.Am) >= self.size_am:
                self._evict_from_am()
            self.A1out.pop(page_id, None)
            self.Am[page_id] = None
            return False

        # 全新页面，进入 A1in，满了按 2Q 规则淘汰
        if len(self.A1in) >= self.size_in:
            self._evict_from_a1in()
        self.A1in[page_id] = None
        return False

    def get_stats(self) -> Dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "a1in": len(self.A1in),
            "a1out": len(self.A1out),
            "am": len(self.Am),
        }
