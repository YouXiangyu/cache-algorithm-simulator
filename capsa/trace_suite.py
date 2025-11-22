from __future__ import annotations

"""
用于缓存性能分析的跟踪序列生成。

本模块定义了9个用于缓存算法比较的负载：
- 3个有利于LFU的负载（WL01-WL03）
- 3个有利于LRU的负载（WL04-WL06）
- 3个其他负载（WL07-WL09）：SCAN和ADAPT模式

所有负载：
- 生成恰好50000次请求
- 为32页缓存大小设计
- 使用基于函数的简单脚本以保证可重现性
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


def _wl01_hot10_80_20() -> PageSequence:
    """
    负载1：热/冷模式（有利于LFU）
    
    模式：
        - 函数A：访问页面1..18（热，80%的访问）
        - 函数B：访问页面19..50（冷，20%的访问）
        - 调度：每10次调用中8×A + 2×B
    
    特征：
        - 强频率偏向：80%的访问集中在18个热页
        - 热集（18页）小于缓存（32），但产生竞争
        - 测试基于频率的算法（LFU）是否优于基于最近使用的算法（LRU）
    """
    seq: PageSequence = []

    def hot() -> None:
        seq.extend(range(1, 19))  # 18页（从10扩展）

    def cold() -> None:
        seq.extend(range(19, 51))  # 32页（从20扩展）

    # 计算：每轮 = 8*18 + 2*32 = 144 + 64 = 208次请求
    # 所需轮数：50000 / 208 ≈ 240
    rounds = 240
    for _ in range(rounds):
        repeat_function(8, hot)
        repeat_function(2, cold)
    
    return trim_to_target(seq, TARGET_REQUESTS, hot)


def _wl02_hot20_60_40() -> PageSequence:
    """
    负载2：扩展的热集（有利于LFU）
    
    模式：
        - 函数A：访问页面1..20（热，60%的访问）
        - 函数B：访问页面21..60（温，40%的访问）
        - 调度：每10次调用中6×A + 4×B
    
    特征：
        - 更大的热集（20页）测试频率与空间的平衡
        - 热集大小匹配缓存大小，产生压力
    """
    seq: PageSequence = []

    def hot() -> None:
        seq.extend(range(1, 21))  # 20页

    def warm() -> None:
        seq.extend(range(21, 61))  # 40页

    # 计算：每轮 = 7*20 + 3*40 = 140 + 120 = 260次请求
    # 所需轮数：50000 / 260 ≈ 192
    rounds = 192
    for _ in range(rounds):
        repeat_function(7, hot)  # 从6增加到7（70%热比例）
        repeat_function(3, warm)  # 从4减少到3
    
    return trim_to_target(seq, TARGET_REQUESTS, hot)


def _wl03_extreme_hot2() -> PageSequence:
    """
    负载3：极端热点（有利于LFU）
    
    模式：
        - 函数A：在页面1和2之间交替（90次访问，占总数的90%）
        - 函数B：顺序访问3..50（48次访问，占总数的10%）
        - 调度：9×A -> 1×B
    
    特征：
        - 极端频率偏向：90%的访问集中在仅2个页面
        - 测试基于频率的算法是否能处理极端情况
        - 背景噪声（B）防止简单优化
    """
    seq: PageSequence = []

    def hot_pair() -> None:
        seq.extend([1, 2] * 45)  # 90次访问：1,2,1,2,...

    def background() -> None:
        seq.extend(range(3, 51))  # 48次访问：3,4,5,...,50

    # 计算：每轮 = 8*90 + 2*48 = 720 + 96 = 816次请求
    # 所需轮数：50000 / 816 ≈ 61
    rounds = 61
    for _ in range(rounds):
        repeat_function(8, hot_pair)  # 从9减少到8（85%热，15%背景）
        background()
        background()  # 添加第二次背景调用
    
    return trim_to_target(seq, TARGET_REQUESTS, hot_pair)


def _generate_sliding_window(
    window_size: int,
    step_size: int,
    max_page: int,
    target_requests: int,
) -> PageSequence:
    """
    生成滑动窗口访问模式。
    
    创建一个页面窗口在页面空间中滑动的序列。
    这是有利于LRU的负载的常见模式。
    
    Args:
        window_size: 滑动窗口的大小
        step_size: 每次移动窗口的位置数（1=连续，>1=跳跃）
        max_page: 最大页码（循环）
        target_requests: 要生成的目标请求数
        
    Returns:
        遵循滑动窗口模式的页面访问序列
    """
    seq: PageSequence = []
    num_windows = target_requests // window_size
    
    # 生成完整窗口
    for i in range(num_windows):
        start = 1 + step_size * i
        for offset in range(window_size):
            page = ((start - 1 + offset) % max_page) + 1
            seq.append(page)
            if len(seq) >= target_requests:
                break
        if len(seq) >= target_requests:
            break
    
    # 添加剩余请求以精确达到目标
    remaining = target_requests - len(seq)
    if remaining > 0:
        start = 1 + step_size * num_windows
        for offset in range(remaining):
            page = ((start - 1 + offset) % max_page) + 1
            seq.append(page)
    
    return seq[:target_requests]


def _wl04_sw32() -> PageSequence:
    """
    负载4：滑动窗口（有利于LRU）
    
    模式：
        - 单个函数：大小为32的滑动窗口（匹配缓存大小）
        - 窗口每次向右滑动1个位置
        - 覆盖页面1..500，循环
    
    特征：
        - 纯最近使用模式：无频率信息
        - 窗口大小匹配缓存，对LRU理想
        - 测试基于最近使用的算法是否优于基于频率的算法
    """
    return _generate_sliding_window(
        window_size=32,
        step_size=1,
        max_page=500,
        target_requests=TARGET_REQUESTS,
    )


def _wl05_sw40() -> PageSequence:
    """
    负载5：更大的滑动窗口（有利于LRU）
    
    模式：
        - 单个函数：大小为40的滑动窗口（大于缓存32）
        - 窗口每次向右滑动1个位置
        - 产生压力：缓存无法容纳整个窗口
    
    特征：
        - 窗口大小（40）> 缓存大小（32），产生驱逐压力
        - 测试LRU处理更大工作集的能力
        - 纯最近使用模式，无频率信息
    """
    return _generate_sliding_window(
        window_size=40,
        step_size=1,
        max_page=600,
        target_requests=TARGET_REQUESTS,
    )


def _wl06_sw32_step2() -> PageSequence:
    """
    负载6：快速滑动窗口（有利于LRU）
    
    模式：
        - 单个函数：大小为32的滑动窗口（匹配缓存）
        - 窗口以步长2移动（比WL04更快）
        - 测试缓存跟踪快速移动工作集的能力
    
    特征：
        - 比WL04移动更快（步长2 vs 步长1）
        - 窗口大小匹配缓存，但移动更快
        - 测试LRU是否能跟上快速变化
    """
    return _generate_sliding_window(
        window_size=32,
        step_size=4,  # Increased from 2 to 4 for faster movement
        max_page=500,
        target_requests=TARGET_REQUESTS,
    )


def _wl07_hot20_scan48000() -> PageSequence:
    """
    负载7：带扫描的热集（SCAN模式，有利于2Q）
    
    模式：
        - 函数A：热集页面1..20
        - 函数B：顺序扫描1..20000（从48000减少）
        - 函数A：再次访问热集页面1..20
        - 调度：750×A -> 1×B -> 750×A
    
    特征：
        - 顺序扫描刷新缓存但不完全
        - 测试扫描抗性：缓存能否在扫描后恢复热集？
        - 2Q算法设计用于处理此模式
        - 总计：15000 + 20000 + 15000 = 50000次请求
    """
    seq: PageSequence = []

    def hot() -> None:
        seq.extend(range(1, 21))  # 20页

    def long_scan() -> None:
        seq.extend(range(1, 20_001))  # 20000页（从48000减少）

    # 阶段1：750 * 20 = 15000次请求
    repeat_function(750, hot)
    # 阶段2：20000次请求（扫描）
    long_scan()
    # 阶段3：750 * 20 = 15000次请求
    repeat_function(750, hot)
    # 总计：50000次请求
    return seq[:TARGET_REQUESTS]


def _wl08_scan_sandwich() -> PageSequence:
    """
    负载8：扫描-热-扫描-热三明治模式（SCAN模式，有利于2Q）
    
    模式：
        - 阶段1：扫描1..15000（15000次请求）
        - 阶段2：热集1..20，50轮（1000次请求）
        - 阶段3：扫描15001..30000（15000次请求）
        - 阶段4：热集1..20，总共400轮（8000次请求）
        - 阶段5：扫描30001..41000（11000次请求）
    
    特征：
        - 热集被扫描"夹在中间"
        - 测试重复刷新后的缓存恢复
        - 2Q算法应比LRU/LFU更好地处理此情况
        - 更平衡：扫描和热阶段交替
        - 总计：15000 + 1000 + 15000 + 8000 + 11000 = 50000次请求
    """
    seq: PageSequence = []
    hot_set = list(range(1, 21))  # 20页
    
    # 阶段1：初始扫描
    seq.extend(range(1, 15001))  # 15000次请求
    
    # 阶段2：第一个热集周期
    for _ in range(50):
        seq.extend(hot_set)  # 50 * 20 = 1000次请求
    
    # 阶段3：第二次扫描
    seq.extend(range(15001, 30001))  # 15000次请求
    
    # 阶段4：扩展的热集周期（从1200轮减少到400轮）
    for _ in range(50):
        seq.extend(hot_set)
    for _ in range(350):  # 从1150减少到350
        seq.extend(hot_set)
    # 阶段4总热集：400轮 = 8000次请求
    
    # 阶段5：最终扫描以达到50000
    # 当前：15000 + 1000 + 15000 + 8000 = 39000
    # 剩余：50000 - 39000 = 11000
    seq.extend(range(30001, 41001))  # 11000次请求
    
    return seq[:TARGET_REQUESTS]


def _wl09_ab_hot_sw32() -> PageSequence:
    """
    负载9：交替的热和滑动窗口（ADAPT模式，有利于ARC）
    
    模式：
        - 阶段A：热模式（8×页面1..10 + 1×冷页跳跃）= 100次请求
        - 阶段B：大小为32的滑动窗口 = 32次请求
        - 调度：A和B交替
    
    特征：
        - 在有利于频率的（A）和有利于最近使用的（B）之间交替
        - 测试可以切换策略的自适应算法（ARC）
        - ARC应在类似LFU（对于A）和类似LRU（对于B）之间适应
        - 每轮：100 + 32 = 132次请求
    """
    seq: PageSequence = []

    def phase_a() -> None:
        """热阶段：8轮热页 + 冷页跳跃。"""
        for _ in range(8):
            seq.extend(range(1, 11))  # 8 * 10 = 80次请求
        # 冷页跳跃：从11..1000中随机20页
        seq.extend([11 + (30 * k % 990) for k in range(20)])  # 20次请求
        # 总计：每个phase_a 100次请求

    def phase_b(step_idx: int) -> None:
        """滑动窗口阶段：32个连续页面。"""
        max_page = 500
        window_size = 32  # 匹配缓存大小
        start = 1 + (step_idx * 7 % (max_page - window_size))
        seq.extend(range(start, start + window_size))
        # 总计：每个phase_b 32次请求

    # 计算：每轮 = 100 + 32 = 132次请求
    # 所需轮数：50000 / 132 ≈ 378
    rounds = 378
    for step_idx in range(rounds):
        phase_a()
        phase_b(step_idx)
    
    return trim_to_target(seq, TARGET_REQUESTS, phase_a)


TRACE_RECIPES: List[TraceRecipe] = [
    TraceRecipe(
        key="WL01_HOT10_80_20",
        filename="WL01_HOT10_80_20.trace",
        category="LFU",
        goal="Highlight: 10 hot pages vs 32 cache, frequency-based should dominate (LFU better)",
        capacity_hint=(32,),
        script=[
            "Function A: access 1..18 (hot)",
            "Function B: access 19..50 (cold)",
            "Schedule: 8×A + 2×B per 10 calls, ~240 rounds",
        ],
        builder=_wl01_hot10_80_20,
    ),
    TraceRecipe(
        key="WL02_HOT20_60_40",
        filename="WL02_HOT20_60_40.trace",
        category="LFU",
        goal="Expand hot set to 20 pages, test frequency vs space balance with 32 cache (LFU better)",
        capacity_hint=(32,),
        script=[
            "Function A: sequential access 1..20",
            "Function B: sequential access 21..60",
            "Schedule: 7×A + 3×B per 10 calls, ~192 rounds",
        ],
        builder=_wl02_hot20_60_40,
    ),
    TraceRecipe(
        key="WL03_EHOT2_90_10",
        filename="WL03_EHOT2_90_10.trace",
        category="LFU",
        goal="Extreme 2-page hot spot (90%), distinguish ARC/LFU from FIFO/LRU (LFU better)",
        capacity_hint=(32,),
        script=[
            "Function A: alternate between pages 1 and 2, 90 accesses",
            "Function B: sequential access 3..50 as background noise",
            "Schedule: 8×A -> 2×B, ~61 rounds",
        ],
        builder=_wl03_extreme_hot2,
    ),
    TraceRecipe(
        key="WL04_SW32",
        filename="WL04_SW32.trace",
        category="LRU",
        goal="Pure recency scenario, window 32 matches cache size for 32 cache (LRU better)",
        capacity_hint=(32,),
        script=[
            "Single function: output window 32 (1..32)",
            "Slide window right by 1 position each time, ~1562 windows, cover 1..500",
        ],
        builder=_wl04_sw32,
    ),
    TraceRecipe(
        key="WL05_SW40",
        filename="WL05_SW40.trace",
        category="LRU",
        goal="Larger sliding window (40 > 32), creates pressure on 32 cache (LRU better)",
        capacity_hint=(32,),
        script=[
            "Single function: output window 40 (1..40)",
            "Slide window right by 1 each time, 1250 windows, cover 1..600",
        ],
        builder=_wl05_sw40,
    ),
    TraceRecipe(
        key="WL06_SW32_STEP2",
        filename="WL06_SW32_STEP2.trace",
        category="LRU",
        goal="Window 32 with step 2, faster movement makes small cache harder to follow (LRU better)",
        capacity_hint=(32,),
        script=[
            "Single function: output window 32",
            "Start position +4 each time, ~1562 windows, cover 1..500",
        ],
        builder=_wl06_sw32_step2,
    ),
    TraceRecipe(
        key="WL07_HOT20_SCAN48000",
        filename="WL07_HOT20_SCAN48000.trace",
        category="SCAN",
        goal="Hot set + long scan, test ARC scan-resistant property (2Q better)",
        capacity_hint=(32,),
        script=[
            "Function A: hot set 1..20",
            "Function B: sequential scan 1..20000",
            "Schedule: 750×A -> 1×B -> 750×A",
        ],
        builder=_wl07_hot20_scan48000,
    ),
    TraceRecipe(
        key="WL08_SCAN_SANDWICH",
        filename="WL08_SCAN_SANDWICH.trace",
        category="SCAN",
        goal="Scan-hot-scan-hot sandwich, test cache recovery after repeated flushing (2Q better)",
        capacity_hint=(32,),
        script=[
            "Phase 1: scan 1..15000",
            "Phase 2: hot set 1..20, 50 rounds",
            "Phase 3: scan 15001..30000",
            "Phase 4: hot set 1..20, 400 rounds",
            "Phase 5: scan 30001..41000",
        ],
        builder=_wl08_scan_sandwich,
    ),
    TraceRecipe(
        key="WL09_AB_HOT_SW32",
        filename="WL09_AB_HOT_SW32.trace",
        category="ADAPT",
        goal="Phase A (hot) and Phase B (sliding window 32) alternate, show ARC adaptivity (ARC adaptive)",
        capacity_hint=(32,),
        script=[
            "Phase A: 8× hot 1..10 + 1× cold page jump",
            "Phase B: window 32 slides in 1..500, ~378 rounds",
            "Overall: A and B alternate",
        ],
        builder=_wl09_ab_hot_sw32,
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

