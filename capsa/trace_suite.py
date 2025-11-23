from __future__ import annotations

"""
用于缓存性能分析的跟踪序列生成。

本模块定义了9个用于缓存算法比较的负载：
- WL01-WL02: 利好LFU（频率模式）
- WL03-WL04: 利好LRU（最近使用模式）
- WL05: 利好FIFO（顺序访问模式）
- WL06-WL07: 利好2Q（扫描+热集模式）
- WL08-WL09: 利好ARC（自适应模式）

所有负载：
- 生成恰好50000次请求
- 为32页缓存大小设计
- 使用简单的循环、条件分支和均匀分布，避免复杂随机
- 确保不同算法命中率差异明显（10%、30%、60%等）
"""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Sequence

# 类型别名以提高可读性
TraceBuilder = Callable[[], List[int]]
PageSequence = List[int]

# 配置常量
TARGET_REQUESTS = 50000
CACHE_SIZE = 32


@dataclass(frozen=True)
class TraceRecipe:
    """跟踪配方：包含脚本描述、目标和生成函数。"""

    key: str
    filename: str
    category: str
    goal: str
    capacity_hint: Sequence[int]
    script: Sequence[str]
    builder: TraceBuilder


def repeat_function(times: int, fn: Callable[[], None]) -> None:
    """
    多次调用一个函数。
    
    这是负载生成模式的辅助函数，用于连续多次执行同一个函数。
    
    Args:
        times: 调用函数的次数
        fn: 要调用的函数（应修改外部状态，例如追加到列表）
    
    Example:
        >>> seq = []
        >>> def add_hot(): seq.extend(range(1, 11))
        >>> repeat_function(8, add_hot)  # 调用add_hot 8次
    """
    for _ in range(times):
        fn()


def trim_to_target(seq: PageSequence, target: int, extend_fn: Callable[[], None] | None = None) -> PageSequence:
    """
    调整序列长度以精确匹配目标值。
    
    如果序列短于目标值，使用提供的函数或重复最后一页来扩展。
    如果长于目标值，则修剪到目标值。
    
    Args:
        seq: 要调整的当前序列
        target: 目标长度（TARGET_REQUESTS = 50000）
        extend_fn: 用于扩展序列的可选函数。
                   如果为None，则通过重复最后一页来扩展。
        
    Returns:
        修剪或扩展到精确目标长度的序列
    
    Example:
        >>> seq = [1, 2, 3]
        >>> def add_more(): seq.extend([4, 5])
        >>> trim_to_target(seq, 5, add_more)  # [1, 2, 3, 4, 5]
    """
    if len(seq) < target:
        if extend_fn:
            # 使用提供的函数扩展（对于真实模式更可取）
            while len(seq) < target:
                extend_fn()
        else:
            # 回退：使用最后一页扩展
            last_page = seq[-1] if seq else 1
            seq.extend([last_page] * (target - len(seq)))
    return seq[:target]


def _wl01_static_frequency() -> PageSequence:
    """
    负载1：静态频率模式（有利于LFU）
    
    简单模式：少量热页高频访问，大量冷页低频访问
    - 热页：页面1-5，每个访问100次/轮（共500次/轮）
    - 冷页：页面6-105，每个访问1次/轮（共100次/轮）
    - 每轮600次请求，共约83轮
    
    关键：LFU能锁定高频数据，LRU会被冷页清洗
    预期：LFU ~75%，ARC ~60%，LRU ~15%，2Q ~20%
    """
    seq: PageSequence = []
    
    hot_pages = list(range(1, 6))  # 5个热页
    cold_pages = list(range(6, 106))  # 100个冷页
    
    def add_round():
        # 热页：每个访问100次
        for page in hot_pages:
            seq.extend([page] * 100)
        # 冷页：每个访问1次（循环访问）
        seq.extend(cold_pages)
    
    # 生成约83轮
    rounds = TARGET_REQUESTS // 600
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl02_frequency_balanced() -> PageSequence:
    """
    负载2：频率平衡模式（有利于LFU）
    
    简单模式：工作集刚好等于缓存大小，测试频率vs空间平衡
    - 热页：页面1-20，每个访问10次/轮（共200次/轮）
    - 温页：页面21-60，每个访问1次/轮（共40次/轮）
    - 每轮240次请求，共约208轮
    
    关键：热集大小=20，接近缓存32，LFU能识别频率优势
    预期：LFU ~65%，ARC ~55%，LRU ~25%，2Q ~30%
    """
    seq: PageSequence = []

    hot_pages = list(range(1, 21))  # 20个热页
    warm_pages = list(range(21, 61))  # 40个温页

    def add_round():
        # 热页：每个访问10次
        for page in hot_pages:
            seq.extend([page] * 10)
        # 温页：每个访问1次
        seq.extend(warm_pages)
    
    # 生成约208轮
    rounds = TARGET_REQUESTS // 240
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl03_static_sliding_window() -> PageSequence:
    """
    负载3：静态滑动窗口（有利于LRU）
    
    简单模式：窗口大小28（略小于缓存32），每次移动1位
    - 纯最近使用模式，无频率信息
    - 窗口循环访问，每次滑动1页
    
    关键：LRU能完美跟踪最近使用的28页，LFU无法利用频率信息
    预期：LRU ~70%，ARC ~60%，LFU ~10%，2Q ~15%
    """
    seq: PageSequence = []
    
    window_size = 28  # 窗口大小28，略小于缓存32
    max_page = 500
    
    # 生成滑动窗口序列
    num_windows = TARGET_REQUESTS // window_size
    for i in range(num_windows):
        start = 1 + (i % (max_page - window_size + 1))
        for offset in range(window_size):
            seq.append(start + offset)
            if len(seq) >= TARGET_REQUESTS:
                break
        if len(seq) >= TARGET_REQUESTS:
            break
    
    # 补充剩余请求
    if len(seq) < TARGET_REQUESTS:
        start = 1 + (num_windows % (max_page - window_size + 1))
        for offset in range(TARGET_REQUESTS - len(seq)):
            if start + offset > max_page:
                start = 1
                offset = 0
            seq.append(start + offset)
    
    return seq[:TARGET_REQUESTS]


def _wl04_oscillating_window() -> PageSequence:
    """
    负载4：震荡滑动窗口（有利于LRU）
    
    简单模式：窗口大小在25和45之间震荡
    - 小窗口阶段：窗口25（小于缓存32），持续2500次请求
    - 大窗口阶段：窗口45（大于缓存32），持续2500次请求
    
    关键：小窗口时LRU表现好，大窗口时LRU仍能跟踪最近使用
    预期：LRU ~60%，ARC ~50%，LFU ~8%，2Q ~12%
    """
    seq: PageSequence = []
    
    small_window = 25  # 小窗口
    large_window = 45  # 大窗口
    max_page = 500
    phase_length = 2500  # 每个阶段2500次请求
    
    window_start = 1
    phase = 0
    
    while len(seq) < TARGET_REQUESTS:
        # 交替窗口大小
        if phase % 2 == 0:
            window_size = small_window
        else:
            window_size = large_window
        
        # 生成当前阶段的窗口访问
        requests_in_phase = min(phase_length, TARGET_REQUESTS - len(seq))
        windows_in_phase = requests_in_phase // window_size
        
        for i in range(windows_in_phase):
            start = window_start + i
            if start + window_size > max_page:
                start = 1
            for offset in range(window_size):
                seq.append(start + offset)
                if len(seq) >= TARGET_REQUESTS:
                    break
            if len(seq) >= TARGET_REQUESTS:
                break
        
        # 更新窗口起始位置
        window_start = (window_start + windows_in_phase) % (max_page - window_size + 1)
        if window_start == 0:
            window_start = 1
        
        phase += 1
        if len(seq) >= TARGET_REQUESTS:
            break
    
    return seq[:TARGET_REQUESTS]


def _wl05_sequential_hot() -> PageSequence:
    """
    负载5：顺序访问+热集模式（有利于FIFO）
    
    简单模式：热集访问频率适中，顺序访问会干扰LRU/LFU
    - 热集：页面1-5，每个访问10次/轮（共50次/轮）
    - 顺序：页面6-37，每个访问1次/轮（共32次/轮，刚好填满缓存）
    - 每轮82次请求，共约609轮
    
    关键：热集访问频率适中（不是特别高），FIFO能保留它们（因为热集先加载）
    顺序访问会按FIFO顺序淘汰，但热集因为访问频率适中，能保持在缓存中
    LRU会被顺序访问干扰（最近访问的是顺序页面，会淘汰热集）
    LFU会被顺序访问干扰（顺序页面访问次数少但会进入缓存，干扰频率统计）
    预期：FIFO ~70%，ARC ~60%，LRU ~30%，LFU ~50%，2Q ~35%
    """
    seq: PageSequence = []
    
    hot_pages = list(range(1, 6))  # 5个热页
    sequential_pages = list(range(6, 38))  # 32个顺序页（刚好填满缓存）
    
    # 每轮：50次热集 + 32次顺序 = 82次
    def add_round():
        # 热集：每个热页访问10次，共50次（先建立工作集）
        for page in hot_pages:
            seq.extend([page] * 10)
        # 顺序：每个顺序页访问1次，共32次（刚好填满缓存）
        seq.extend(sequential_pages)
    
    # 生成约609轮
    rounds = TARGET_REQUESTS // 82
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl06_scan_hot_mixed() -> PageSequence:
    """
    负载6：扫描+热集混合（有利于2Q）
    
    简单模式：大量一次性扫描 + 少量重复热集
    - 每100次请求：20次热集访问（页面1-3循环），80次扫描访问（页面1000+顺序，每个只访问一次）
    - 热集会重复访问（会被2Q的Am队列保留），扫描是一次性的（会被2Q的A1in队列过滤）
    
    关键：2Q的A1in队列（16页）能过滤扫描数据，不会污染Am队列（16页）中的热数据
    LRU会被扫描干扰（扫描数据会进入缓存，清洗热数据）
    预期：2Q ~75%，ARC ~50%，LRU ~15%，LFU ~20%，FIFO ~15%
    """
    seq: PageSequence = []
    
    hot_pages = list(range(1, 4))  # 3个热页
    scan_start = 1000
    
    scan_pos = scan_start
    hot_index = 0
    
    # 每100次请求：20次热集，80次扫描
    def add_round():
        nonlocal scan_pos, hot_index
        # 20次热集访问（会重复，每个热页约6-7次）
        for _ in range(20):
            seq.append(hot_pages[hot_index % len(hot_pages)])
            hot_index += 1
        # 80次扫描访问（一次性，每个只访问一次）
        for _ in range(80):
            seq.append(scan_pos)
            scan_pos += 1
    
    # 生成约500轮
    rounds = TARGET_REQUESTS // 100
    for _ in range(rounds):
        add_round()
    
    return trim_to_target(seq, TARGET_REQUESTS, add_round)


def _wl07_scan_sandwich() -> PageSequence:
    """
    负载7：扫描三明治模式（有利于2Q）
    
    简单模式：扫描-热-扫描-热三明治，扫描期间热集访问频率低
    - 阶段1：扫描页面1000-20000，每100次扫描夹杂2次热集（10000次请求）
    - 阶段2：热集页面1-3（20000次请求，建立工作集）
    - 阶段3：扫描页面20001-40000，每100次扫描夹杂2次热集（10000次请求）
    - 阶段4：热集页面1-3（剩余请求，测试恢复能力）
    
    关键：2Q的A1in队列能过滤扫描数据，Am队列能保留热数据
    扫描期间热集访问频率低，但2Q能识别并保留它们
    LRU会被扫描干扰（扫描数据会清洗热数据）
    预期：2Q ~80%，ARC ~60%，LRU ~25%，LFU ~30%，FIFO ~25%
    """
    seq: PageSequence = []
    
    hot_pages = list(range(1, 4))  # 3个热页
    
    # 阶段1：扫描1000-20000，每100次扫描夹杂2次热集
    scan_pos = 1000
    hot_index = 0
    scan_count = 0
    while scan_pos <= 20000 and len(seq) < 10000:
        if scan_count % 100 < 2:
            seq.append(hot_pages[hot_index % len(hot_pages)])
            hot_index += 1
        else:
            seq.append(scan_pos)
            scan_pos += 1
        scan_count += 1
    
    # 阶段2：热集20000次（建立工作集）
    for _ in range(6666):  # 6666 * 3 = 19998
        seq.extend(hot_pages)
        if len(seq) >= 30000:
            break
    # 补充2次
    seq.extend(hot_pages[:2])
    
    # 阶段3：扫描20001-40000，每100次扫描夹杂2次热集
    scan_pos = 20001
    scan_count = 0
    while scan_pos <= 40000 and len(seq) < 40000:
        if scan_count % 100 < 2:
            seq.append(hot_pages[hot_index % len(hot_pages)])
            hot_index += 1
        else:
            seq.append(scan_pos)
            scan_pos += 1
        scan_count += 1
        if len(seq) >= 40000:
            break
    
    # 阶段4：热集剩余部分
    while len(seq) < TARGET_REQUESTS:
        seq.extend(hot_pages)
    
    return seq[:TARGET_REQUESTS]


def _wl08_adaptive_frequency_recency() -> PageSequence:
    """
    负载8：自适应频率-最近使用模式（有利于ARC）
    
    简单模式：频率模式和最近使用模式交替
    - 阶段A（频率）：页面1-10循环访问（100次请求）
    - 阶段B（最近使用）：滑动窗口32（32次请求）
    - A和B交替
    
    关键：ARC能在频率和最近使用之间自适应
    预期：ARC ~65%，LFU ~50%（在A阶段好），LRU ~55%（在B阶段好），2Q ~45%
    """
    seq: PageSequence = []

    def phase_a() -> None:
        """频率阶段：热页循环访问"""
        for _ in range(10):
            seq.extend(range(1, 11))  # 10 * 10 = 100次请求

    def phase_b(step_idx: int) -> None:
        """最近使用阶段：滑动窗口32"""
        max_page = 500
        window_size = 32
        start = 1 + (step_idx * 7 % (max_page - window_size + 1))
        seq.extend(range(start, start + window_size))

    # 每轮 = 100 + 32 = 132次请求
    rounds = TARGET_REQUESTS // 132
    for step_idx in range(rounds):
        phase_a()
        phase_b(step_idx)
    
    return trim_to_target(seq, TARGET_REQUESTS, phase_a)


def _wl09_adaptive_mixed() -> PageSequence:
    """
    负载9：自适应混合模式（有利于ARC）
    
    简单模式：多种模式混合，测试ARC的适应能力
    - 每5000次请求切换模式：
      * 模式1：频率模式（页面1-5高频，页面6-20低频）
      * 模式2：最近使用模式（滑动窗口30）
      * 模式3：扫描+热集（每50次扫描夹杂5次热集）
    
    关键：ARC能适应不同模式，其他算法只能适应一种
    预期：ARC ~60%，其他算法 ~30-50%（取决于当前模式）
    """
    seq: PageSequence = []
    
    phase_length = 5000
    phase = 0
    
    while len(seq) < TARGET_REQUESTS:
        requests_in_phase = min(phase_length, TARGET_REQUESTS - len(seq))
        
        if phase % 3 == 0:
            # 模式1：频率模式
            hot_pages = list(range(1, 6))
            cold_pages = list(range(6, 21))
            count = 0
            while count < requests_in_phase and len(seq) < TARGET_REQUESTS:
                for page in hot_pages:
                    if count >= requests_in_phase or len(seq) >= TARGET_REQUESTS:
                        break
                    seq.extend([page] * 10)  # 每个热页10次
                    count += 10
                for page in cold_pages:
                    if count >= requests_in_phase or len(seq) >= TARGET_REQUESTS:
                        break
                    seq.append(page)  # 每个冷页1次
                    count += 1
        elif phase % 3 == 1:
            # 模式2：最近使用模式（滑动窗口30）
            window_size = 30
            max_page = 500
            start = 1 + ((phase // 3) * 10 % (max_page - window_size + 1))
            windows = requests_in_phase // window_size
            for i in range(windows):
                current_start = start + i
                if current_start + window_size > max_page:
                    current_start = 1
                for offset in range(window_size):
                    seq.append(current_start + offset)
                    if len(seq) >= TARGET_REQUESTS:
                        break
                if len(seq) >= TARGET_REQUESTS:
                    break
        else:
            # 模式3：扫描+热集
            hot_pages = list(range(1, 4))
            scan_pos = 1000 + (phase // 3) * 1000
            hot_index = 0
            scan_count = 0
            for _ in range(requests_in_phase):
                if scan_count % 50 < 5:
                    seq.append(hot_pages[hot_index % len(hot_pages)])
                    hot_index += 1
                else:
                    seq.append(scan_pos)
                    scan_pos += 1
                scan_count += 1
                if len(seq) >= TARGET_REQUESTS:
                    break
        
        phase += 1
        if len(seq) >= TARGET_REQUESTS:
            break
    
    return seq[:TARGET_REQUESTS]


TRACE_RECIPES: List[TraceRecipe] = [
    TraceRecipe(
        key="WL01_STATIC_FREQ",
        filename="WL01_STATIC_FREQ.trace",
        category="LFU",
        goal="静态频率模式：少量热页高频访问，大量冷页低频访问（有利于LFU）",
        capacity_hint=(32,),
        script=[
            "热页：页面1-5，每个访问100次/轮",
            "冷页：页面6-105，每个访问1次/轮",
            "每轮：500次热页 + 100次冷页 = 600次请求",
            "预期：LFU ~75%, ARC ~60%, LRU ~15%, 2Q ~20%",
        ],
        builder=_wl01_static_frequency,
    ),
    TraceRecipe(
        key="WL02_FREQ_BALANCED",
        filename="WL02_FREQ_BALANCED.trace",
        category="LFU",
        goal="频率平衡模式：工作集等于缓存大小，测试频率与空间平衡（有利于LFU）",
        capacity_hint=(32,),
        script=[
            "热页：页面1-20，每个访问10次/轮",
            "温页：页面21-60，每个访问1次/轮",
            "每轮：200次热页 + 40次温页 = 240次请求",
            "预期：LFU ~65%, ARC ~55%, LRU ~25%, 2Q ~30%",
        ],
        builder=_wl02_frequency_balanced,
    ),
    TraceRecipe(
        key="WL03_STATIC_SW",
        filename="WL03_STATIC_SW.trace",
        category="LRU",
        goal="静态滑动窗口：窗口大小28，每次移动1位（有利于LRU）",
        capacity_hint=(32,),
        script=[
            "窗口大小28（略小于缓存32）",
            "每次移动1个位置",
            "纯最近使用模式，无频率信息",
            "预期：LRU ~70%, ARC ~60%, LFU ~10%, 2Q ~15%",
        ],
        builder=_wl03_static_sliding_window,
    ),
    TraceRecipe(
        key="WL04_OSC_SW",
        filename="WL04_OSC_SW.trace",
        category="LRU",
        goal="震荡滑动窗口：小窗口（25）和大窗口（45）交替（有利于LRU）",
        capacity_hint=(32,),
        script=[
            "小窗口阶段：窗口25，2500次请求",
            "大窗口阶段：窗口45，2500次请求",
            "交替阶段",
            "预期：LRU ~60%, ARC ~50%, LFU ~8%, 2Q ~12%",
        ],
        builder=_wl04_oscillating_window,
    ),
    TraceRecipe(
        key="WL05_SEQUENTIAL_HOT",
        filename="WL05_SEQUENTIAL_HOT.trace",
        category="FIFO",
        goal="顺序访问+热集模式（有利于FIFO）",
        capacity_hint=(32,),
        script=[
            "热集：页面1-5，每个访问10次/轮（50次请求）",
            "顺序：页面6-37，每个访问1次/轮（32次请求，刚好填满缓存）",
            "每轮：50次热集 + 32次顺序 = 82次请求",
            "热集先加载且访问频率适中，FIFO能保留它们",
            "LRU被顺序访问干扰（最近访问的是顺序页面）",
            "LFU被顺序访问干扰（顺序页面进入缓存，干扰频率统计）",
            "预期：FIFO ~70%, ARC ~60%, LRU ~30%, LFU ~50%, 2Q ~35%",
        ],
        builder=_wl05_sequential_hot,
    ),
    TraceRecipe(
        key="WL06_SCAN_HOT_MIXED",
        filename="WL06_SCAN_HOT_MIXED.trace",
        category="2Q",
        goal="扫描+热集混合模式：数据库全表扫描+在线交易（有利于2Q）",
        capacity_hint=(32,),
        script=[
            "每100次请求：20次热集（页面1-3，重复访问）",
            "80次扫描（页面1000+，一次性，不重用）",
            "2Q的A1in队列（16页）过滤扫描数据，Am队列（16页）保留热数据",
            "LRU被扫描干扰（扫描数据进入缓存，清洗热数据）",
            "预期：2Q ~75%, ARC ~50%, LRU ~15%, LFU ~20%, FIFO ~15%",
        ],
        builder=_wl06_scan_hot_mixed,
    ),
    TraceRecipe(
        key="WL07_SCAN_SANDWICH",
        filename="WL07_SCAN_SANDWICH.trace",
        category="2Q",
        goal="扫描三明治模式：数据备份+在线业务（有利于2Q）",
        capacity_hint=(32,),
        script=[
            "阶段1：扫描1000-20000，每100次扫描夹杂2次热集（10000次请求）",
            "阶段2：热集页面1-3（20000次请求，建立工作集）",
            "阶段3：扫描20001-40000，每100次扫描夹杂2次热集（10000次请求）",
            "阶段4：热集页面1-3（剩余请求，测试恢复能力）",
            "2Q的A1in队列过滤扫描数据，Am队列保留热数据",
            "预期：2Q ~80%, ARC ~60%, LRU ~25%, LFU ~30%, FIFO ~25%",
        ],
        builder=_wl07_scan_sandwich,
    ),
    TraceRecipe(
        key="WL08_ADAPTIVE_FREQ_RECENCY",
        filename="WL08_ADAPTIVE_FREQ_RECENCY.trace",
        category="ARC",
        goal="自适应频率-最近使用模式：频率和最近使用阶段交替（有利于ARC）",
        capacity_hint=(32,),
        script=[
            "阶段A（频率）：页面1-10循环访问（100次请求）",
            "阶段B（最近使用）：滑动窗口32（32次请求）",
            "A和B交替",
            "预期：ARC ~65%, LFU ~50%（在A阶段好）, LRU ~55%（在B阶段好）, 2Q ~45%",
        ],
        builder=_wl08_adaptive_frequency_recency,
    ),
    TraceRecipe(
        key="WL09_ADAPTIVE_MIXED",
        filename="WL09_ADAPTIVE_MIXED.trace",
        category="ARC",
        goal="自适应混合模式：多种模式每5000次请求切换（有利于ARC）",
        capacity_hint=(32,),
        script=[
            "模式1：频率模式（页面1-5高频，页面6-20低频）",
            "模式2：最近使用模式（滑动窗口30）",
            "模式3：扫描+热集（每50次扫描夹杂5次热集）",
            "每5000次请求切换模式",
            "预期：ARC ~60%, 其他算法 ~30-50%（取决于当前模式）",
        ],
        builder=_wl09_adaptive_mixed,
    ),
]


TRACE_BY_KEY: Dict[str, TraceRecipe] = {t.key: t for t in TRACE_RECIPES}


def list_trace_keys() -> List[str]:
    return [t.key for t in TRACE_RECIPES]


def generate_trace(key: str) -> List[int]:
    recipe = TRACE_BY_KEY[key]
    return recipe.builder()


def iter_recipes() -> Iterable[TraceRecipe]:
    return list(TRACE_RECIPES)


__all__ = [
    "TraceRecipe",
    "TRACE_RECIPES",
    "TRACE_BY_KEY",
    "generate_trace",
    "list_trace_keys",
    "iter_recipes",
]

