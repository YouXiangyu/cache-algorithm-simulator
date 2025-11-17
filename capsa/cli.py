from __future__ import annotations

from typing import Callable, Dict, Iterable, List

from .caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache
from .metrics import MetricsCollector, ReportConfig
from .simulator import Simulator
from .trace_generator import TraceGenerator, WorkloadType


def _prompt_int(
    message: str, default: int | None = None, minimum: int | None = None, maximum: int | None = None
) -> int:
    while True:
        raw = input(f"{message} " + (f"[默认 {default}]: " if default is not None else ": "))
        raw = raw.strip()
        if not raw and default is not None:
            raw = str(default)
        try:
            value = int(raw)
            if minimum is not None and value < minimum:
                raise ValueError
            if maximum is not None and value > maximum:
                raise ValueError
            return value
        except ValueError:
            limit = ""
            if minimum is not None or maximum is not None:
                limit = f" ({minimum or '-∞'} - {maximum or '∞'})"
            print(f"请输入有效的整数{limit}。")


def _prompt_float(
    message: str, default: float, minimum: float | None = None, maximum: float | None = None
) -> float:
    while True:
        raw = input(f"{message} [默认 {default}]: ").strip()
        if not raw:
            return default
        try:
            value = float(raw)
            if minimum is not None and value < minimum:
                raise ValueError
            if maximum is not None and value > maximum:
                raise ValueError
            return value
        except ValueError:
            limit = ""
            if minimum is not None or maximum is not None:
                limit = f" ({minimum or '-∞'} - {maximum or '∞'})"
            print(f"请输入有效的数字{limit}。")


def _select_from_menu(message: str, options: Dict[str, str]) -> str:
    print(message)
    for key, text in options.items():
        print(f"{key}: {text}")
    while True:
        choice = input("> ").strip()
        if choice in options:
            return choice
        print("无效的选项，请重新选择。")


def _print_hint(title: str, meaning: str, range_text: str, effect: str) -> None:
    print(f"- {title}: {meaning}。范围：{range_text}。{effect}")


def _collect_workload_params(workload_type: WorkloadType) -> Dict[str, int | float]:
    if workload_type is WorkloadType.STATIC:
        print(
            "静态负载说明：热点集越大意味着更多页面会被频繁重复访问；扫描集越大表示一次性顺序读取的数据更多。"
        )
        _print_hint("总请求数", "Trace 长度", "1 - 1,000,000", "越大越平滑，运行时间也更长")
        _print_hint("页面总数", "潜在页面的全集规模", "2 - 100,000", "越大越分散，命中率可能下降")
        _print_hint("热点数据占比", "热点访问概率", "0.0 - 1.0", "越大越偏向重复访问")
        _print_hint("扫描数据占比", "顺序扫描概率", "0.0 - 1.0", "越大越考验缓存对突发扫描的适应力")
        return {
            "total_requests": _prompt_int("请输入总请求数 (1-1000000)", 20000, minimum=1, maximum=1_000_000),
            "total_pages": _prompt_int("请输入页面总数 (2-100000)", 1000, minimum=2, maximum=100_000),
            "hot_ratio": _prompt_float("请输入热点数据占比 (0-1)", 0.8, minimum=0.0, maximum=1.0),
            "scan_ratio": _prompt_float("请输入扫描数据占比 (0-1)", 0.2, minimum=0.0, maximum=1.0),
        }
    if workload_type is WorkloadType.DYNAMIC:
        print(
            "动态负载说明：热点阶段反复访问固定集合，扫描阶段顺序访问新页面；阶段越多，热点与扫描交替越频繁。"
        )
        _print_hint("总请求数", "Trace 长度", "1 - 1,000,000", "越大越能看到长期趋势")
        _print_hint("热点集大小", "被高频访问的页面数量", "1 - 50,000", "越大越接近均匀随机访问")
        _print_hint("扫描长度", "每次顺序扫描的页数", "1 - 100,000", "越大越容易冲掉缓存内容")
        _print_hint("阶段数量", "热点/扫描循环的次数", "1 - 50", "越大越频繁切换访问模式")
        return {
            "total_requests": _prompt_int("请输入总请求数 (1-1000000)", 20000, minimum=1, maximum=1_000_000),
            "hot_set_size": _prompt_int("请输入热点集大小 (1-50000)", 100, minimum=1, maximum=50_000),
            "scan_length": _prompt_int("请输入扫描长度 (1-100000)", 500, minimum=1, maximum=100_000),
            "phases": _prompt_int("请输入阶段数量 (1-50)", 4, minimum=1, maximum=50),
        }
    print(
        "震荡负载说明：周期性在热点访问和扫描访问之间来回切换，切换越频繁越容易产生抖动（thrashing）。"
    )
    _print_hint("震荡周期数", "热点+扫描的重复次数", "1 - 50", "越大持续时间越长")
    _print_hint("每次热点访问次数", "每个周期内连续热点请求数量", "1 - 50,000", "越大越有利于缓存保持命中")
    _print_hint("每次扫描长度", "每个周期的顺序扫描规模", "1 - 50,000", "越大越容易清空缓存内容")
    _print_hint("热点集大小", "热点阶段涉及的不同页面数量", "1 - 50,000", "越大越稀释热点效应")
    return {
        "cycles": _prompt_int("请输入震荡周期数 (1-50)", 5, minimum=1, maximum=50),
        "hot_burst": _prompt_int("请输入每次热点访问次数 (1-50000)", 2000, minimum=1, maximum=50_000),
        "scan_burst": _prompt_int("请输入每次扫描长度 (1-50000)", 2000, minimum=1, maximum=50_000),
        "hot_set_size": _prompt_int("请输入热点集大小 (1-50000)", 100, minimum=1, maximum=50_000),
    }


def _build_cache_factories(cache_size: int, trace: Iterable[int]) -> Dict[str, Callable[[], OPTCache | ARCCache | LRUCache | LFUCache | FIFOCache]]:
    trace_list = list(trace)
    return {
        "LRU": lambda: LRUCache(cache_size),
        "LFU": lambda: LFUCache(cache_size),
        "FIFO": lambda: FIFOCache(cache_size),
        "ARC": lambda: ARCCache(cache_size),
        "OPT": lambda: OPTCache(cache_size, trace_list),
    }


def run_cli() -> None:
    print("Welcome to the Cache Algorithm Performance Simulator & Analyzer (CAPSA)!")
    cache_size = _prompt_int("请输入缓存大小 (例如 256)", 256, minimum=1)

    algo_choice = _select_from_menu(
        "请选择要运行的缓存算法：",
        {
            "1": "LRU",
            "2": "LFU",
            "3": "FIFO",
            "4": "ARC",
            "5": "OPT",
            "6": "ALL",
        },
    )

    workload_choice = _select_from_menu(
        "请选择工作负载类型：",
        {
            "1": "Static",
            "2": "Dynamic",
            "3": "Oscillating",
        },
    )

    workload_map = {
        "1": WorkloadType.STATIC,
        "2": WorkloadType.DYNAMIC,
        "3": WorkloadType.OSCILLATING,
    }
    workload_type = workload_map[workload_choice]
    print(f"配置 {workload_type.value.upper()} 工作负载...")
    workload_params = _collect_workload_params(workload_type)

    trace_generator = TraceGenerator(workload_type, workload_params)
    trace = trace_generator.generate()

    factories = _build_cache_factories(cache_size, trace)

    if algo_choice == "6":
        selected_algorithms = list(factories.keys())
    else:
        mapping = {"1": "LRU", "2": "LFU", "3": "FIFO", "4": "ARC", "5": "OPT"}
        selected_algorithms = [mapping[algo_choice]]

    simulator = Simulator(cache_size, trace)
    results = []

    for name in selected_algorithms:
        cache = factories[name]()
        print(f"运行 {name} 模拟...")
        result = simulator.run(name, cache)
        results.append(result)

    report_config = ReportConfig(
        cache_size=cache_size,
        workload_name=workload_type.value.title(),
        workload_params=workload_params,
        total_requests=len(trace),
    )
    collector = MetricsCollector(report_config)

    print("\n" + collector.build_report(results))


