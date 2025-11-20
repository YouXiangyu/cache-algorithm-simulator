from __future__ import annotations

from typing import Callable, Dict, Iterable, List

from .caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache, TwoQCache
from .metrics import MetricsCollector, ReportConfig
from .simulator import Simulator, SimulationResult
from .trace_generator import TraceGenerator, WorkloadType


LANGUAGE_PACKS = {
    "zh": {
        "welcome": "欢迎使用 CAPSA（缓存算法性能模拟与分析器）！",
        "cache_prompt": "请输入缓存大小（示例 256）",
        "algo_menu_title": "请选择要运行的缓存算法（可输入多个序号，用逗号或空格分隔）：",
        "algo_hint": "示例：输入 1,3 表示运行 LRU 与 FIFO；输入 7 表示运行全部。",
        "algo_options": {
            "1": "LRU（最近最少使用）",
            "2": "LFU（最不常用）",
            "3": "FIFO（先进先出）",
            "4": "ARC（自适应替换缓存）",
            "5": "OPT（理论最优）",
            "6": "2Q（双队列）",
            "7": "ALL（全部算法）",
        },
        "algo_invalid": "无效的算法编号，请重新输入。",
        "menu_invalid": "无效的选项，请重新输入。",
        "workload_menu_title": "请选择工作负载类型：",
        "workload_options": {"1": "静态 (Static)", "2": "动态 (Dynamic)", "3": "震荡 (Oscillating)"},
        "configure_workload": "正在配置 {name} 工作负载...",
        "total_requests": "总请求数",
        "total_pages": "页面总数",
        "hot_ratio": "热点数据占比",
        "scan_ratio": "扫描数据占比",
        "hot_set_size": "热点集大小",
        "scan_length": "扫描长度",
        "phases": "阶段数量",
        "cycles": "震荡周期数",
        "hot_burst": "每次热点访问次数",
        "scan_burst": "每次扫描长度",
        "hint_prefix": "【参数提示】",
        "prompt_language": "请选择语言 / Please choose language (zh/en) [默认 zh]: ",
        "invalid_language": "输入无效，请输入 zh 或 en。",
        "int_error": "请输入有效的整数{limit}。",
        "float_error": "请输入有效的数字{limit}。",
        "run_algorithm": "开始运行 {name} 模拟...",
        "input_suffix": "（默认 {default}）: ",
        "input_suffix_plain": ": ",
        "run_count_prompt": "运行次数 (1=单次运行, >1=批量测试) [默认 1]",
        "batch_start": "开始批量测试...",
        "run": "运行",
        "batch_complete": "批量测试完成，正在汇总结果...",
    },
    "en": {
        "welcome": "Welcome to CAPSA (Cache Algorithm Performance Simulator & Analyzer)!",
        "cache_prompt": "Enter cache size (e.g. 256)",
        "algo_menu_title": "Select cache algorithms to run (multiple indices allowed, comma or space separated):",
        "algo_hint": "Example: 1,3 runs LRU and FIFO; enter 7 to run ALL.",
        "algo_options": {
            "1": "LRU (Least Recently Used)",
            "2": "LFU (Least Frequently Used)",
            "3": "FIFO (First-In First-Out)",
            "4": "ARC (Adaptive Replacement Cache)",
            "5": "OPT (Optimal / Belady)",
            "6": "2Q (Two Queues)",
            "7": "ALL (run every algorithm)",
        },
        "algo_invalid": "Invalid algorithm selection, please try again.",
        "menu_invalid": "Invalid choice, please try again.",
        "workload_menu_title": "Select workload type:",
        "workload_options": {"1": "Static", "2": "Dynamic", "3": "Oscillating"},
        "configure_workload": "Configuring {name} workload...",
        "total_requests": "Total Requests",
        "total_pages": "Total Pages",
        "hot_ratio": "Hot Ratio",
        "scan_ratio": "Scan Ratio",
        "hot_set_size": "Hot Set Size",
        "scan_length": "Scan Length",
        "phases": "Phase Count",
        "cycles": "Oscillation Cycles",
        "hot_burst": "Hot Burst Length",
        "scan_burst": "Scan Burst Length",
        "hint_prefix": "[Parameter Tips]",
        "prompt_language": "请选择语言 / Please choose language (zh/en) [default zh]: ",
        "invalid_language": "Invalid input, please type zh or en.",
        "int_error": "Please enter a valid integer{limit}.",
        "float_error": "Please enter a valid number{limit}.",
        "run_algorithm": "Running {name} simulation...",
        "input_suffix": " (default {default}): ",
        "input_suffix_plain": ": ",
        "run_count_prompt": "Number of runs (1=single, >1=batch) [default 1]",
        "batch_start": "Starting batch testing...",
        "run": "Run",
        "batch_complete": "Batch testing complete, aggregating results...",
    },
}

WORKLOAD_INTROS = {
    WorkloadType.STATIC: {
        "zh": "【静态负载】热点集越大，重复访问越明显；扫描集越大，说明顺序读取占比越高。",
        "en": "[Static] Larger hot sets amplify repeated hits; larger scan sets mean more sequential sweeps.",
    },
    WorkloadType.DYNAMIC: {
        "zh": "【动态负载】热点阶段与扫描阶段交替出现，阶段越多，模式切换越频繁。",
        "en": "[Dynamic] Alternates between hot bursts and scans; more phases mean more frequent shifts.",
    },
    WorkloadType.OSCILLATING: {
        "zh": "【震荡负载】在热点与扫描之间快速切换，可模拟 thrashing 场景。",
        "en": "[Oscillating] Rapidly switches between hot and scan phases to stress adaptability.",
    },
}

PARAM_HINTS = {
    WorkloadType.STATIC: [
        {
            "title": {"zh": "总请求数", "en": "Total Requests"},
            "meaning": {"zh": "Trace 总长度", "en": "Total length of the trace"},
            "range": "1 - 1,000,000",
            "effect": {
                "zh": "越大越平滑，但模拟时间更长",
                "en": "Higher values smooth stats but take longer to simulate",
            },
        },
        {
            "title": {"zh": "页面总数", "en": "Total Pages"},
            "meaning": {"zh": "潜在页面全集规模", "en": "Universe size of possible pages"},
            "range": "2 - 100,000",
            "effect": {
                "zh": "越大越分散，命中率通常下降",
                "en": "Larger means sparser reuse, often lowering hit rate",
            },
        },
        {
            "title": {"zh": "热点数据占比", "en": "Hot Ratio"},
            "meaning": {"zh": "访问热点集合的概率", "en": "Probability of drawing from the hot set"},
            "range": "0 - 1",
            "effect": {
                "zh": "越大越偏向重复访问",
                "en": "Higher ratio favors repeated hits",
            },
        },
        {
            "title": {"zh": "扫描数据占比", "en": "Scan Ratio"},
            "meaning": {"zh": "进入顺序扫描的概率", "en": "Probability of sequential scan"},
            "range": "0 - 1",
            "effect": {
                "zh": "越大越容易冲掉缓存",
                "en": "Higher ratio purges cache more often",
            },
        },
    ],
    WorkloadType.DYNAMIC: [
        {
            "title": {"zh": "总请求数", "en": "Total Requests"},
            "meaning": {"zh": "Trace 总长度", "en": "Total length of the trace"},
            "range": "1 - 1,000,000",
            "effect": {
                "zh": "越大越能观察长期趋势",
                "en": "Larger captures longer-term trends",
            },
        },
        {
            "title": {"zh": "热点集大小", "en": "Hot Set Size"},
            "meaning": {"zh": "热点阶段涉及的页面数", "en": "Unique pages during hot bursts"},
            "range": "1 - 50,000",
            "effect": {
                "zh": "越大越接近均匀随机访问",
                "en": "Bigger sets dilute temporal locality",
            },
        },
        {
            "title": {"zh": "扫描长度", "en": "Scan Length"},
            "meaning": {"zh": "每次扫描访问的连续新页数", "en": "Length of each sequential sweep"},
            "range": "1 - 100,000",
            "effect": {
                "zh": "越大越容易清空缓存",
                "en": "Longer scans eject more cached pages",
            },
        },
        {
            "title": {"zh": "阶段数量", "en": "Phase Count"},
            "meaning": {"zh": "热点/扫描交替的次数", "en": "How many hot/scan alternations"},
            "range": "1 - 50",
            "effect": {
                "zh": "越大模式切换越频繁",
                "en": "More phases mean faster oscillations",
            },
        },
    ],
    WorkloadType.OSCILLATING: [
        {
            "title": {"zh": "震荡周期数", "en": "Oscillation Cycles"},
            "meaning": {"zh": "热点+扫描重复次数", "en": "How many hot+scan repetitions"},
            "range": "1 - 50",
            "effect": {
                "zh": "越大持续时间越长",
                "en": "Higher cycles extend total runtime",
            },
        },
        {
            "title": {"zh": "每次热点访问次数", "en": "Hot Burst Length"},
            "meaning": {"zh": "单次热点阶段的请求数", "en": "Requests within each hot burst"},
            "range": "1 - 50,000",
            "effect": {
                "zh": "越大越容易维持命中",
                "en": "Longer bursts favor cache warmup",
            },
        },
        {
            "title": {"zh": "每次扫描长度", "en": "Scan Burst Length"},
            "meaning": {"zh": "单次扫描阶段的请求数", "en": "Requests within each scan burst"},
            "range": "1 - 50,000",
            "effect": {
                "zh": "越大越容易产生抖动",
                "en": "Longer scans trigger more thrashing",
            },
        },
        {
            "title": {"zh": "热点集大小", "en": "Hot Set Size"},
            "meaning": {"zh": "热点阶段会访问的不同页面数量", "en": "Unique hot pages per cycle"},
            "range": "1 - 50,000",
            "effect": {
                "zh": "越大越稀释热点效果",
                "en": "Bigger sets reduce locality benefits",
            },
        },
    ],
}

PARAM_SPECS = {
    WorkloadType.STATIC: [
        {
            "name": "total_requests",
            "type": "int",
            "default": 20000,
            "min": 1,
            "max": 1_000_000,
            "prompt": {
                "zh": "请输入总请求数 (1-1000000)",
                "en": "Enter total requests (1-1,000,000)",
            },
        },
        {
            "name": "total_pages",
            "type": "int",
            "default": 1000,
            "min": 2,
            "max": 100_000,
            "prompt": {"zh": "请输入页面总数 (2-100000)", "en": "Enter total pages (2-100,000)"},
        },
        {
            "name": "hot_ratio",
            "type": "float",
            "default": 0.8,
            "min": 0.0,
            "max": 1.0,
            "prompt": {"zh": "请输入热点数据占比 (0-1)", "en": "Enter hot ratio (0-1)"},
        },
        {
            "name": "scan_ratio",
            "type": "float",
            "default": 0.2,
            "min": 0.0,
            "max": 1.0,
            "prompt": {"zh": "请输入扫描数据占比 (0-1)", "en": "Enter scan ratio (0-1)"},
        },
    ],
    WorkloadType.DYNAMIC: [
        {
            "name": "total_requests",
            "type": "int",
            "default": 20000,
            "min": 1,
            "max": 1_000_000,
            "prompt": {
                "zh": "请输入总请求数 (1-1000000)",
                "en": "Enter total requests (1-1,000,000)",
            },
        },
        {
            "name": "hot_set_size",
            "type": "int",
            "default": 100,
            "min": 1,
            "max": 50_000,
            "prompt": {"zh": "请输入热点集大小 (1-50000)", "en": "Enter hot set size (1-50,000)"},
        },
        {
            "name": "scan_length",
            "type": "int",
            "default": 500,
            "min": 1,
            "max": 100_000,
            "prompt": {"zh": "请输入扫描长度 (1-100000)", "en": "Enter scan length (1-100,000)"},
        },
        {
            "name": "phases",
            "type": "int",
            "default": 4,
            "min": 1,
            "max": 50,
            "prompt": {"zh": "请输入阶段数量 (1-50)", "en": "Enter number of phases (1-50)"},
        },
    ],
    WorkloadType.OSCILLATING: [
        {
            "name": "cycles",
            "type": "int",
            "default": 5,
            "min": 1,
            "max": 50,
            "prompt": {"zh": "请输入震荡周期数 (1-50)", "en": "Enter oscillation cycles (1-50)"},
        },
        {
            "name": "hot_burst",
            "type": "int",
            "default": 2000,
            "min": 1,
            "max": 50_000,
            "prompt": {
                "zh": "请输入每次热点访问次数 (1-50000)",
                "en": "Enter hot burst length (1-50,000)",
            },
        },
        {
            "name": "scan_burst",
            "type": "int",
            "default": 2000,
            "min": 1,
            "max": 50_000,
            "prompt": {
                "zh": "请输入每次扫描长度 (1-50000)",
                "en": "Enter scan burst length (1-50,000)",
            },
        },
        {
            "name": "hot_set_size",
            "type": "int",
            "default": 100,
            "min": 1,
            "max": 50_000,
            "prompt": {"zh": "请输入热点集大小 (1-50000)", "en": "Enter hot set size (1-50,000)"},
        },
    ],
}


def _select_language() -> str:
    while True:
        raw = input(LANGUAGE_PACKS["zh"]["prompt_language"]).strip().lower()
        if not raw:
            return "zh"
        if raw in ("zh", "en"):
            return raw
        print(LANGUAGE_PACKS["zh"]["invalid_language"])


def _prompt_int(
    message: str,
    language: str,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    texts = LANGUAGE_PACKS[language]
    suffix = texts["input_suffix"] if default is not None else texts["input_suffix_plain"]
    while True:
        raw = input(f"{message}{suffix.format(default=default)}").strip()
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
            print(texts["int_error"].format(limit=limit))


def _prompt_float(
    message: str,
    language: str,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    texts = LANGUAGE_PACKS[language]
    suffix = texts["input_suffix"]
    while True:
        raw = input(f"{message}{suffix.format(default=default)}").strip()
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
            print(texts["float_error"].format(limit=limit))


def _select_from_menu(message: str, options: Dict[str, str], language: str) -> str:
    print(f"\n{message}")
    for key, text in options.items():
        print(f"  {key}: {text}")
    texts = LANGUAGE_PACKS[language]
    while True:
        choice = input("> ").strip()
        if choice in options:
            return choice
        print(texts["menu_invalid"])


def _print_hint(title: str, meaning: str, range_text: str, effect: str, language: str) -> None:
    bullet = "-"
    connector = "。范围：" if language == "zh" else ". Range: "
    tail = "。" if language == "zh" else ". "
    print(f"{bullet} {title}: {meaning}{connector}{range_text}{tail}{effect}")


def _collect_workload_params(workload_type: WorkloadType, language: str) -> Dict[str, int | float]:
    intro = WORKLOAD_INTROS[workload_type][language]
    texts = LANGUAGE_PACKS[language]
    print(f"\n{texts['hint_prefix']} {intro}")
    for hint in PARAM_HINTS[workload_type]:
        _print_hint(
            hint["title"][language],
            hint["meaning"][language],
            hint["range"],
            hint["effect"][language],
            language,
        )

    params: Dict[str, int | float] = {}
    for spec in PARAM_SPECS[workload_type]:
        prompt_text = spec["prompt"][language]
        if spec["type"] == "int":
            params[spec["name"]] = _prompt_int(
                prompt_text,
                language,
                default=spec["default"],
                minimum=spec["min"],
                maximum=spec["max"],
            )
        else:
            params[spec["name"]] = _prompt_float(
                prompt_text,
                language,
                default=spec["default"],
                minimum=spec["min"],
                maximum=spec["max"],
            )
    return params


def _build_cache_factories(
    cache_size: int, trace: Iterable[int]
) -> Dict[str, Callable[[], OPTCache | ARCCache | LRUCache | LFUCache | FIFOCache | TwoQCache]]:
    trace_list = list(trace)
    return {
        "LRU": lambda: LRUCache(cache_size),
        "LFU": lambda: LFUCache(cache_size),
        "FIFO": lambda: FIFOCache(cache_size),
        "ARC": lambda: ARCCache(cache_size),
        "OPT": lambda: OPTCache(cache_size, trace_list),
        "2Q": lambda: TwoQCache(cache_size),
    }


def _parse_algorithm_selection(raw_input: str, language: str) -> List[str]:
    mapping = {"1": "LRU", "2": "LFU", "3": "FIFO", "4": "ARC", "5": "OPT", "6": "2Q"}
    cleaned = raw_input.replace(",", " ").split()
    selected = []
    for token in cleaned:
        if token not in mapping:
            print(LANGUAGE_PACKS[language]["algo_invalid"])
            return []
        algo = mapping[token]
        if algo not in selected:
            selected.append(algo)
    if not selected:
        print(LANGUAGE_PACKS[language]["algo_invalid"])
    return selected


def _prompt_algorithm_selection(language: str) -> List[str] | None:
    texts = LANGUAGE_PACKS[language]
    options = texts["algo_options"]
    print(f"\n{texts['algo_menu_title']}")
    for key, description in options.items():
        print(f"  {key}: {description}")
    print(texts["algo_hint"])
    while True:
        choice = input("> ").strip()
        if choice == "7":
            return None
        selection = _parse_algorithm_selection(choice, language)
        if selection:
            return selection


def run_cli() -> None:
    language = _select_language()
    texts = LANGUAGE_PACKS[language]
    print(f"\n{texts['welcome']}\n" + "=" * 60)
    cache_size = _prompt_int(texts["cache_prompt"], language, default=256, minimum=1)

    algo_selection = _prompt_algorithm_selection(language)

    workload_choice = _select_from_menu(texts["workload_menu_title"], texts["workload_options"], language)

    workload_map = {
        "1": WorkloadType.STATIC,
        "2": WorkloadType.DYNAMIC,
        "3": WorkloadType.OSCILLATING,
    }
    workload_type = workload_map[workload_choice]
    workload_name_display = texts["workload_options"][workload_choice]
    print(f"\n{texts['configure_workload'].format(name=workload_name_display.upper())}")
    workload_params = _collect_workload_params(workload_type, language)

    # 询问运行次数
    run_count = _prompt_int(
        texts.get("run_count_prompt", "运行次数 (1=单次, >1=批量测试) [默认 1]"),
        language,
        default=1,
        minimum=1,
        maximum=10000,
    )

    # 确定要运行的算法列表
    if algo_selection is None:
        selected_algorithms = ["LRU", "LFU", "FIFO", "ARC", "OPT", "2Q"]
    else:
        selected_algorithms = algo_selection

    # 收集所有运行的结果
    all_results_by_algorithm: Dict[str, List[SimulationResult]] = {name: [] for name in selected_algorithms}

    print(f"\n{texts.get('batch_start', '开始批量测试...')}")
    for run_idx in range(run_count):
        if run_count > 1:
            print(f"\n[{texts.get('run', '运行')} {run_idx + 1}/{run_count}]")

        # 每次运行使用不同的随机种子生成新的trace
        trace_generator = TraceGenerator(workload_type, workload_params, seed=None if run_count == 1 else run_idx)
        trace = trace_generator.generate()

        factories = _build_cache_factories(cache_size, trace)
        simulator = Simulator(cache_size, trace)

        for name in selected_algorithms:
            cache = factories[name]()
            if run_count == 1:
                print(f"\n{texts['run_algorithm'].format(name=name)}")
            result = simulator.run(name, cache)
            all_results_by_algorithm[name].append(result)

    # 汇总结果
    if run_count == 1:
        # 单次运行：直接使用原始结果
        results = [all_results_by_algorithm[name][0] for name in selected_algorithms]
        report_config = ReportConfig(
            cache_size=cache_size,
            workload_name=workload_type.value.title(),
            workload_params=workload_params,
            total_requests=len(trace),
        )
        collector = MetricsCollector(report_config)
        print("\n" + collector.build_report(results))
    else:
        # 批量运行：计算平均值
        print(f"\n{texts.get('batch_complete', '批量测试完成，正在汇总结果...')}")
        report_config = ReportConfig(
            cache_size=cache_size,
            workload_name=workload_type.value.title(),
            workload_params=workload_params,
            total_requests=len(trace),  # 使用最后一次的trace长度作为参考
        )
        collector = MetricsCollector(report_config)
        print("\n" + collector.build_batch_report(all_results_by_algorithm, run_count))


