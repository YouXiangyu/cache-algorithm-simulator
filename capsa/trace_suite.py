from __future__ import annotations

"""
用于缓存性能分析的跟踪序列生成。

本模块定义了9个用于缓存算法比较的负载：
- WL01-WL02: 利好LFU（频率模式）
- WL03-WL04: 利好LRU（最近使用模式）
- WL05: 利好FIFO（队列车队/污染模式）
- WL06: 利好ARC（频率-最近使用切换）
- WL07: 利好2Q（扫描+热集模式）
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


def _wl05_fifo_convoy() -> PageSequence:
    """
    LFU 毒药：缓存污染模式
    
    场景：
    1. 前期高频访问 Group A (造成 LFU 计数虚高)
    2. 后期切换到 Group B (循环访问)
    
    预期结果：
    - LFU: 极低。因为它死守着 counts 极高的 Group A，导致 Group B 进不来。
    - FIFO: 极高。它会自然代谢掉 Group A，适应 Group B。
    """
    seq: PageSequence = []
    
    # 假设缓存大小 = 32
    cache_size = 32
    
    # 1. 污染阶段 (Pollution Phase)
    # 让页面 1-32 积累极高的频率 (每个访问 50 次)
    pollution_pages = list(range(1, 33))
    for _ in range(50):
        seq.extend(pollution_pages)
        
    # 2. 切换阶段 (Phase Shift)
    # 完全抛弃 1-32，转而循环访问 33-64
    # 注意：这里新页面数量 <= 缓存大小，只要进了缓存就能 100% 命中
    working_set = list(range(33, 65)) # 32个新页面
    
    # 填充剩余的请求数
    current_len = len(seq)
    remaining_requests = TARGET_REQUESTS - current_len
    
    # 简单的循环填充
    rounds = remaining_requests // len(working_set) + 1
    for _ in range(rounds):
        seq.extend(working_set)
        
    return trim_to_target(seq, TARGET_REQUESTS)


def _wl06_adaptive_frequency_recency() -> PageSequence:
    """
    负载6：自适应频率-最近使用模式（有利于ARC）
    
    阶段交替：
    - 阶段A：页面1-10循环访问100次（累积频率优势）
    - 阶段B：32页滑动窗口，窗口每轮漂移（强调最近使用）
    
    关键：ARC 可根据命中反馈动态调整 T1/T2 大小，应对频率与最近使用的快速切换。
    """
    seq: PageSequence = []

    def phase_a() -> None:
        """频率阶段：热页循环访问"""
        for _ in range(10):
            seq.extend(range(1, 11))

    def phase_b(step_idx: int) -> None:
        """最近使用阶段：滑动窗口32"""
        max_page = 500
        window_size = 32
        start = 1 + (step_idx * 7 % (max_page - window_size + 1))
        seq.extend(range(start, start + window_size))

    # 每轮 = 132 次请求
    rounds = TARGET_REQUESTS // 132
    for step_idx in range(rounds):
        phase_a()
        phase_b(step_idx)

    return trim_to_target(seq, TARGET_REQUESTS, phase_a)


def _wl07_scan_sandwich() -> PageSequence:
    """
    负载7：WL08 自适应改编 II（热集漂移 + 双滑窗 + 长扫描）
    
    模式组合：
    - 热浪：三个10页热集依次访问，频率从高到低
    - 滑窗I：32页窗口执行两次，窗口位置每轮漂移
    - 热桥：热集1与热集3交替，模拟恢复阶段
    - 滑窗II：48页窗口执行两次，考察更大的最近使用集合
    - 冷扫描：200页一次性访问，重置频率记忆
    
    重复上述组合直至达到50000次请求。
    """
    seq: PageSequence = []

    hot_sets = [
        list(range(1, 11)),
        list(range(11, 21)),
        list(range(31, 41)),
    ]
    hot_repeats = (5, 4, 3)

    window_size_small = 32
    window_size_large = 48
    max_page = 900

    small_span = max_page - window_size_small - 49
    large_span = max_page - window_size_large - 99

    def add_cycle(step: int) -> None:
        for block, reps in zip(hot_sets, hot_repeats):
            for _ in range(reps):
                seq.extend(block)

        start_small = 50 + (step * 19 % max(1, small_span))
        seq.extend(range(start_small, start_small + window_size_small))

        start_small_2 = 100 + (step * 23 % max(1, small_span))
        seq.extend(range(start_small_2, start_small_2 + window_size_small))

        for _ in range(3):
            seq.extend(hot_sets[0])
            seq.extend(hot_sets[2])

        start_large = 150 + (step * 29 % max(1, large_span))
        seq.extend(range(start_large, start_large + window_size_large))
        start_large_2 = 220 + (step * 31 % max(1, large_span))
        seq.extend(range(start_large_2, start_large_2 + window_size_large))

        scan_base = 4000 + step * 200
        seq.extend(range(scan_base, scan_base + 200))

    cycle_length = (
        sum(len(block) * reps for block, reps in zip(hot_sets, hot_repeats))
        + window_size_small * 2
        + (len(hot_sets[0]) + len(hot_sets[2])) * 3
        + window_size_large * 2
        + 200
    )
    cycles = TARGET_REQUESTS // cycle_length

    for step in range(cycles):
        add_cycle(step)

    step = cycles
    while len(seq) < TARGET_REQUESTS:
        add_cycle(step)
        step += 1

    return seq[:TARGET_REQUESTS]


def _wl08_arc_mosaic() -> PageSequence:
    """
    负载8：ARC 杂合模式（简化版）
    
    每轮串联四段简单模式，突出 ARC 在频率/最近使用/冷扫描之间的自适应：
    1. 高频块A：页面1-6快速循环12次（72次请求）
    2. 滑动窗口：30页窗口一次扫描，窗口位置随轮漂移
    3. 高频块B：页面31-36循环6次（36次请求）+ 桥接页面90-105
    4. 冷扫描：60页一次性访问，随后短暂回到两个热集
    
    结构类似 WL09 的多模式混合，但规模更小、描述更简单。
    """
    seq: PageSequence = []

    hot_a = list(range(1, 7))
    hot_b = list(range(31, 37))
    bridge = list(range(90, 106))  # 16页
    window_size = 30
    max_window_page = 900

    def add_cycle(step: int) -> None:
        # 1) 高频块A
        for _ in range(12):
            seq.extend(hot_a)

        # 2) 滑动窗口
        start = 200 + (step * 23 % max(1, max_window_page - window_size - 200))
        seq.extend(range(start, start + window_size))

        # 3) 高频块B + 桥接
        for _ in range(6):
            seq.extend(hot_b)
        seq.extend(bridge)

        # 4) 冷扫描 + 热集恢复
        scan_base = 1200 + step * 60
        seq.extend(range(scan_base, scan_base + 60))
        seq.extend(hot_a)
        seq.extend(hot_b)

    cycle_length = len(hot_a) * 12 + window_size + len(hot_b) * 6 + len(bridge) + 60 + len(hot_a) + len(hot_b)
    cycles = TARGET_REQUESTS // cycle_length

    for step in range(cycles):
        add_cycle(step)

    step = cycles
    while len(seq) < TARGET_REQUESTS:
        add_cycle(step)
        step += 1

    return seq[:TARGET_REQUESTS]


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
        key="WL05_FIFO_CONVOY",
        filename="WL05_FIFO_CONVOY.trace",
        category="FIFO",
        goal="队列车队模式：严格顺序循环 + 轻微扰动（极有利于FIFO）",
        capacity_hint=(32,),
        script=[
            "车队主体：页面1-32，固定顺序循环（每轮6次）",
            "第一次循环填充缓存，其余循环几乎全命中",
            "尾部扰动：页面200-215，用于轻度刷新 FIFO 队列",
            "扰动确保 FIFO 淘汰顺序与下一轮车队首部对齐",
            "FIFO ~90%, OPT ~92%，其余算法受扰动影响更大",
        ],
        builder=_wl05_fifo_convoy,
    ),
    TraceRecipe(
        key="WL06_ADAPTIVE_FREQ_RECENCY",
        filename="WL06_ADAPTIVE_FREQ_RECENCY.trace",
        category="ARC",
        goal="自适应频率-最近使用模式（原WL08，现迁移至WL06）",
        capacity_hint=(32,),
        script=[
            "阶段A：页面1-10循环访问（100次请求）",
            "阶段B：滑动窗口32（32次请求），窗口随轮漂移",
            "A/B交替，迫使算法在频率与最近使用之间切换",
            "ARC动态调节T1/T2，更稳健；LRU/LFU/2Q只能偏向一侧",
            "预期：ARC ~65%, LFU ~50%, LRU ~55%, 2Q ~45%, FIFO ~40%",
        ],
        builder=_wl06_adaptive_frequency_recency,
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
        key="WL08_ARC_MOSAIC",
        filename="WL08_ARC_MOSAIC.trace",
        category="ARC",
        goal="ARC 杂合模式：热集A/B + 滑动窗口 + 冷扫描（有利于ARC）",
        capacity_hint=(32,),
        script=[
            "阶段A：页面1-6循环12次，建立频率优势",
            "阶段B：30页滑动窗口一次扫描，窗口随轮漂移",
            "阶段C：页面31-36循环6次 + 桥接页90-105，模拟热集切换",
            "阶段D：60页冷扫描后短暂回到两个热集，形成完整杂合",
            "预期：ARC ~68%, LRU ~48%, LFU ~50%, 2Q ~52%, FIFO ~38%",
        ],
        builder=_wl08_arc_mosaic,
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

