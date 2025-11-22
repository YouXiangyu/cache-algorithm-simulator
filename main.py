"""
缓存性能分析主模块。

本模块提供两种使用模式：
1. 命令行数字参数模式：python main.py -1
2. 交互式CLI菜单模式：python main.py

所有模拟使用固定缓存大小（32页）和固定请求数（每个负载50000次请求）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Dict, List

from capsa.caches import ARCCache, FIFOCache, LFUCache, LRUCache, OPTCache, TwoQCache
from capsa.metrics import MetricsCollector, ReportConfig
from capsa.simulator import Simulator
from capsa.trace_suite import TRACE_BY_KEY, TRACE_RECIPES, generate_trace

# 配置常量
CACHE_SIZE = 32
ALGORITHMS = ["LRU", "LFU", "FIFO", "ARC", "OPT", "2Q"]


def build_cache_factories(cache_size: int, trace: List[int]) -> Dict[str, Callable[[], object]]:
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
        "2Q": lambda: TwoQCache(cache_size),
    }


def run_simulation(
    cache_size: int,
    trace: List[int],
    source_name: str,
    *,
    workload_name: str | None = None,
    workload_params: Dict[str, object] | None = None,
) -> str:
    """
    在跟踪序列上运行模拟并生成性能报告。
    
    Args:
        cache_size: 缓存大小（页数）
        trace: 页面访问序列
        source_name: 跟踪源名称（例如文件名）
        workload_name: 可选的负载类别名称
        workload_params: 可选的负载参数字典
        
    Returns:
        格式化的性能报告字符串
    """
    factories = build_cache_factories(cache_size, trace)
    simulator = Simulator(cache_size, trace)
    results = []
    
    for algo_name in ALGORITHMS:
        cache = factories[algo_name]()
        results.append(simulator.run(algo_name, cache))
    
    report_config = ReportConfig(
        cache_size=cache_size,
        workload_name=workload_name or "File",
        workload_params=workload_params or {"source": source_name},
        total_requests=len(trace),
    )
    collector = MetricsCollector(report_config)
    return collector.build_report(results)


def run_workload(cache_size: int, recipe_key: str) -> None:
    """
    通过键运行单个负载并打印报告。
    
    Args:
        cache_size: 缓存大小（页数）
        recipe_key: 标识负载配方的键
    """
    recipe = TRACE_BY_KEY[recipe_key]
    trace = generate_trace(recipe_key)
    params = {
        "recipe": recipe.key,
        "category": recipe.category,
        "steps": list(recipe.script),
        "capacity_hint": list(recipe.capacity_hint),
    }
    report = run_simulation(
        cache_size,
        trace,
        recipe.filename,
        workload_name=recipe.category,
        workload_params=params,
    )
    print(report)


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
        arg: 参数字符串（例如，"-1" 或 "WL01_HOT10_80_20"）
        
    Returns:
        (workload_index, workload_key)元组，其中一个是None
    """
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
    
    raise ValueError(f"Unknown workload '{arg}'. Use workload numbers (1-9) or workload keys like 'WL01_HOT10_80_20'")


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
        epilog="Examples:\n  python main.py -1          # Run workload 1\n  python main.py -1 -3 -5    # Run workloads 1, 3, 5\n  python main.py             # Interactive menu",
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
