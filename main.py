"""
缓存性能分析主模块。

本模块提供三种使用模式：
1. 命令行数字参数模式：python main.py -1
2. 交互式CLI菜单模式：python main.py
3. 汇总模式：python main.py -all（运行所有负载并显示汇总表）

所有模拟使用固定缓存大小（32页）和固定请求数（每个负载50000次请求）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict, List

from capsa.caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache, TwoQCache
from capsa.metrics import MetricsCollector, ReportConfig
from capsa.simulator import Simulator, SimulationResult
from capsa.trace_suite import TRACE_BY_KEY, TRACE_RECIPES, generate_trace

# 配置常量
CACHE_SIZE = 32
ALGORITHMS = ["LFU", "LRU", "FIFO", "2Q", "ARC", "OPT"]
NON_OPT_ALGOS = [algo for algo in ALGORITHMS if algo != "OPT"]
WORKLOAD_COL_WIDTH = 10
VALUE_COL_WIDTH = 12
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_GREEN = "\033[32m"
SUPPORTS_ANSI = sys.stdout.isatty()
TWO_Q_A1OUT_FIXED = 32
TWO_Q_A1IN_MAX = 16


def tune_two_q_offline(cache_size: int, trace: List[int]) -> tuple[int, float]:
    """
    针对给定负载离线搜索 2Q 的最佳 A1in 大小，A1out 固定为 16。
    返回 (best_a1in, best_hit_rate)。
    """
    simulator = Simulator(cache_size, trace)
    search_upper = min(TWO_Q_A1IN_MAX, cache_size - 1)
    best_a1in = 1
    best_hit_rate = -1.0
    
    for a1in in range(1, search_upper + 1):
        cache = TwoQCache(cache_size, a1in_size=a1in, a1out_size=TWO_Q_A1OUT_FIXED)
        result = simulator.run("2Q", cache)
        if result.hit_rate > best_hit_rate:
            best_hit_rate = result.hit_rate
            best_a1in = a1in
    
    return best_a1in, best_hit_rate


def emphasize_best_cell(text: str) -> str:
    """
    使用 ANSI 颜色与下划线高亮最佳命中率。
    在 stdout 不支持 ANSI 时，直接返回原文本以保持对齐。
    """
    if not SUPPORTS_ANSI:
        return text
    return f"{ANSI_BOLD}{ANSI_GREEN}{text}{ANSI_RESET}"


def build_cache_factories(
    cache_size: int,
    trace: List[int],
    *,
    two_q_params: Dict[str, object] | None = None,
) -> Dict[str, Callable[[], object]]:
    """
    为所有缓存算法构建工厂函数。
    
    Args:
        cache_size: 缓存大小（页数）
        trace: 完整的跟踪序列（OPT算法需要）
        
    Returns:
        算法名称到工厂函数的字典映射
    """
    return {
        "LRU": lambda: LRUCache(cache_size),
        "LFU": lambda: LFUCache(cache_size),
        "FIFO": lambda: FIFOCache(cache_size),
        "ARC": lambda: ARCCache(cache_size),
        "OPT": lambda: OPTCache(cache_size, trace),
        "2Q": lambda: TwoQCache(cache_size, **(two_q_params or {})),
    }


def run_workload(cache_size: int, recipe_key: str, silent: bool = False) -> List[SimulationResult]:
    """
    通过键运行单个负载并返回结果。
    
    Args:
        cache_size: 缓存大小（页数）
        recipe_key: 标识负载配方的键
        silent: 如果为True，不打印详细报告
        
    Returns:
        模拟结果列表
    """
    recipe = TRACE_BY_KEY[recipe_key]
    trace = generate_trace(recipe_key)
    best_a1in, best_two_q_hit = tune_two_q_offline(cache_size, trace)
    two_q_params = {"a1in_size": best_a1in, "a1out_size": TWO_Q_A1OUT_FIXED}
    factories = build_cache_factories(cache_size, trace, two_q_params=two_q_params)
    simulator = Simulator(cache_size, trace)
    results = []
    
    for algo_name in ALGORITHMS:
        cache = factories[algo_name]()
        results.append(simulator.run(algo_name, cache))
    
    if not silent:
        params = {
            "recipe": recipe.key,
            "category": recipe.category,
            "steps": list(recipe.script),
            "capacity_hint": list(recipe.capacity_hint),
            "two_q_best_a1in": best_a1in,
            "two_q_best_hit_rate": round(best_two_q_hit, 2),
        }
        report_config = ReportConfig(
            cache_size=cache_size,
            workload_name=recipe.category,
            workload_params=params,
            total_requests=len(trace),
        )
        collector = MetricsCollector(report_config)
        print(collector.build_report(results))
        print(f"[2Q offline tuning] A1in={best_a1in}, A1out={TWO_Q_A1OUT_FIXED}, HitRate={best_two_q_hit:.2f}%")
    
    return results


def extract_better_indicator(goal: str) -> str:
    """
    从负载目标字符串中提取"更好"的指示符。
    
    Args:
        goal: 可能包含指示符（如"(LFU better)"）的目标字符串
        
    Returns:
        如果找到则返回指示符字符串，否则返回空字符串
    """
    indicators = ["(LFU better)", "(LRU better)", "(2Q better)", "(ARC adaptive)"]
    for indicator in indicators:
        if indicator in goal:
            return indicator
    return ""


def format_workload_description(recipe) -> tuple[str, str]:
    """
    格式化负载描述以便在菜单中显示。
    
    Args:
        recipe: TraceRecipe对象
        
    Returns:
        (indicator, clean_goal)元组，其中indicator是"更好"的指示符，
        clean_goal是不包含指示符的目标
    """
    indicator = extract_better_indicator(recipe.goal)
    clean_goal = recipe.goal
    for ind in ["(LFU better)", "(LRU better)", "(2Q better)", "(ARC adaptive)"]:
        clean_goal = clean_goal.replace(ind, "")
    clean_goal = clean_goal.strip()
    return indicator, clean_goal


def display_workload_menu() -> None:
    """显示交互式负载选择菜单。"""
    print("\n" + "=" * 60)
    print("Cache Performance Analysis - Workload Selection")
    print("=" * 60)
    print(f"\nCache Size: {CACHE_SIZE} pages")
    print(f"Requests per workload: 50000\n")
    print("Available Workloads:")
    print("-" * 60)
    
    for idx, recipe in enumerate(TRACE_RECIPES, 1):
        indicator, clean_goal = format_workload_description(recipe)
        print(f"{idx}. {recipe.key} {indicator}")
        print(f"   {clean_goal}")
    
    print("-" * 60)
    print("\nEnter workload numbers (1-9) separated by spaces or commas (e.g., 1 3 5 or 1,3,5):")
    print("Or press Enter to run all workloads:")


def parse_user_selection(user_input: str, num_workloads: int) -> List[int]:
    """
    解析用户输入的负载选择。
    
    Args:
        user_input: 原始用户输入字符串
        num_workloads: 可用负载总数
        
    Returns:
        选中的负载索引列表（从1开始）
    """
    if not user_input.strip():
        return list(range(1, num_workloads + 1))
    
    selections = []
    for part in user_input.replace(",", " ").split():
        try:
            num = int(part)
            if 1 <= num <= num_workloads:
                selections.append(num)
            else:
                print(f"Warning: {num} is out of range (1-{num_workloads}), ignoring.")
        except ValueError:
            print(f"Warning: '{part}' is not a valid number, ignoring.")
    
    if not selections:
        print("No valid selections. Running all workloads.")
        return list(range(1, num_workloads + 1))
    
    return sorted(set(selections))  # Remove duplicates and sort


def show_interactive_menu() -> List[int]:
    """
    显示交互式CLI菜单并返回选中的负载索引。
    
    Returns:
        选中的负载索引列表（从1开始），如果取消则返回空列表
    """
    display_workload_menu()
    
    try:
        user_input = input("> ").strip()
        return parse_user_selection(user_input, len(TRACE_RECIPES))
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return []


def parse_workload_argument(arg: str) -> tuple[int | None, str | None]:
    """
    解析负载参数（数字或键）。
    
    Args:
        arg: 参数字符串（例如，"-1" 或 "WL01_HOT10_80_20" 或 "-all"）
        
    Returns:
        (workload_index, workload_key)元组，其中一个是None，如果是-all则返回(-1, None)
    """
    # 检查是否为-all参数
    if arg.lower() == "-all" or arg.lower() == "--all":
        return -1, None
    
    # 检查是否为数字参数（负数如-1）
    if arg.startswith("-") and arg[1:].isdigit():
        num = int(arg[1:])  # 移除减号
        if 1 <= num <= len(TRACE_RECIPES):
            return num, None
        else:
            raise ValueError(f"Workload number {num} is out of range (1-{len(TRACE_RECIPES)})")
    
    # 检查是否为负载键
    if arg in TRACE_BY_KEY:
        return None, arg
    
    raise ValueError(f"Unknown workload '{arg}'. Use workload numbers (1-9), workload keys, or -all to run all workloads")


def run_all_workloads_summary() -> None:
    """
    运行所有负载并显示美观的命中率汇总表格。
    """
    print("\n" + "=" * 80)
    print("CAPSA - Running all workloads with summary table")
    print("=" * 80)
    print(f"\nCache size: {CACHE_SIZE} pages")
    print(f"Requests per workload: 50000\n")
    print("Running all workloads, please wait...\n")
    
    # 收集所有负载的结果
    all_results: Dict[str, Dict[str, float]] = {}
    
    for idx, recipe in enumerate(TRACE_RECIPES, 1):
        print(f"Running workload {idx}/9: {recipe.key}...", end=" ", flush=True)
        results = run_workload(CACHE_SIZE, recipe.key, silent=True)
        
        # 提取命中率
        workload_results = {}
        for result in results:
            workload_results[result.algorithm] = result.hit_rate
        all_results[f"WL{idx:02d}"] = workload_results
        print("Done")
    
    # 生成美观的表格
    print("\n" + "=" * 80)
    print("Hit rate summary (%)")
    print("=" * 80 + "\n")
    
    # 表头与分隔线
    header_cells = [f"{'Workload':<{WORKLOAD_COL_WIDTH}}"]
    header_cells.extend(f"{algo:>{VALUE_COL_WIDTH}}" for algo in ALGORITHMS)
    header = " ".join(header_cells)
    table_width = len(header.replace(ANSI_BOLD, "").replace(ANSI_GREEN, "").replace(ANSI_RESET, ""))
    print(header)
    print("-" * table_width)
    
    # 数据行并突出每个负载的最佳命中率
    for workload_name in sorted(all_results.keys()):
        workload_results = all_results[workload_name]
        best_hit_rate = (
            max((workload_results.get(algo, 0.0) for algo in NON_OPT_ALGOS), default=0.0)
            if workload_results
            else 0.0
        )
        row_cells = [f"{workload_name:<{WORKLOAD_COL_WIDTH}}"]
        for algo in ALGORITHMS:
            hit_rate = workload_results.get(algo, 0.0)
            cell = f"{hit_rate:>{VALUE_COL_WIDTH}.2f}"
            if algo != "OPT" and abs(hit_rate - best_hit_rate) < 1e-9:
                cell = emphasize_best_cell(cell)
            row_cells.append(cell)
        print(" ".join(row_cells))
    
    print("\n" + "=" * 80)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """
    解析命令行参数。
    
    Args:
        argv: 命令行参数（不包括脚本名称）
        
    Returns:
        解析后的参数命名空间
    """
    parser = argparse.ArgumentParser(
        description="CAPSA - Cache Algorithm Performance Simulator & Analyzer",
        epilog="Examples:\n  python main.py -1          # Run workload 1\n  python main.py -1 -3 -5    # Run workloads 1, 3, 5\n  python main.py -all         # Run all workloads with summary table\n  python main.py             # Interactive menu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "workloads",
        nargs="*",
        help="Workload numbers (1-9) or workload keys. Use -1 for workload 1, etc.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """
    缓存性能分析器的主入口点。
    
    支持两种模式：
    1. 命令行模式：python main.py -1（运行负载1）
    2. 交互模式：python main.py（显示菜单）
    """
    # 检查是否为-all参数（需要在parse_arguments之前处理）
    if len(sys.argv) > 1 and (sys.argv[1].lower() == "-all" or sys.argv[1].lower() == "--all"):
        run_all_workloads_summary()
        return
    
    args = parse_arguments(sys.argv[1:])
    
    # 解析负载参数
    selected_indices: List[int] = []
    workload_keys: List[str] = []
    
    for arg in args.workloads:
        try:
            idx, key = parse_workload_argument(arg)
            if idx is not None:
                selected_indices.append(idx)
            elif key is not None:
                workload_keys.append(key)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    # 如果未提供参数，显示交互菜单
    if not selected_indices and not workload_keys:
        selected_indices = show_interactive_menu()
        if not selected_indices:
            return
    
    # 运行选中的负载
    for idx in selected_indices:
        recipe = TRACE_RECIPES[idx - 1]  # 转换为从0开始的索引
        print(f"\n{'=' * 60}")
        print(f"Running Workload {idx}: {recipe.key}")
        print(f"{'=' * 60}\n")
        run_workload(CACHE_SIZE, recipe.key)
    
    for key in workload_keys:
        print(f"\n{'=' * 60}")
        print(f"Running Workload: {key}")
        print(f"{'=' * 60}\n")
        run_workload(CACHE_SIZE, key)


if __name__ == "__main__":
    main()
