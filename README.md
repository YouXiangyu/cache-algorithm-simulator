# CAPSA - Cache Algorithm Performance Simulator & Analyzer

- 创建/更新时间：2025-11-17

CAPSA 是一个可配置的缓存替换算法模拟器，用于比较 ARC、LRU、LFU、FIFO、2Q 以及理论最优 OPT 算法在不同工作负载下的表现。项目采用模块化设计，方便扩展新的算法与工作负载。

## 功能特性

- `Simulator`：驱动 trace 访问，测量命中率与 `cache.access()` 调用开销。
- `TraceGenerator`：内置静态 / 动态 / 震荡三种工作负载，支持参数化生成请求序列。
- `Cache` 抽象类：定义统一接口；提供 ARC/LRU/LFU/FIFO/2Q/OPT 实现。
- `MetricsCollector`：计算命中率、加权总耗时（命中=1、未命中=10）、平均算法开销并输出报告。
- CLI：交互式收集缓存大小、算法、工作负载及其参数，可一次运行全部算法。

## 环境要求

- Python 3.10+

## 快速开始

```bash
cd D:\code\ARC_project
python main.py
```

按提示依次输入缓存大小、算法、工作负载类型及对应参数。程序会自动生成访问序列并输出各算法的性能报告。

## 目录结构

```
capsa/
  cache_base.py        # 缓存抽象类
  caches/              # 各缓存算法实现
  trace_generator.py   # 工作负载生成
  simulator.py         # 主模拟器
  metrics.py           # 指标与报告
  cli.py               # CLI 交互入口
main.py                # 程序入口
```

## 后续计划

- 支持从真实 trace 文件加载。
- 增加更多性能指标（例如带宽、并发访问）。
- 提供可视化图表输出。


