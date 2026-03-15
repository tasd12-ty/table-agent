"""SpreadsheetBench 评估脚本

用法:
    uv run python scripts/run_bench.py \
        --data-dir data/spreadsheetbench/all_data_912_v0.1 \
        --limit 10 \
        --concurrency 3 \
        --max-rounds 5 \
        -v
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 将项目根目录加入 sys.path 以便导入 table_agent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from table_agent.bench.comparator import SpreadsheetComparator
from table_agent.bench.dataset import BenchmarkDataset
from table_agent.bench.report import BenchmarkReporter
from table_agent.bench.runner import BenchmarkRunner
from table_agent.config import load_config
from table_agent.llm import LLMClient
from table_agent.react.agent import ReactAgent
from table_agent.react.executor import CodeExecutor
from table_agent.react.renderer import SpreadsheetRenderer
from table_agent.react.tracer import TraceRecorder

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SpreadsheetBench 评估 - ReAct Agent",
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help="SpreadsheetBench 数据目录 (默认读取 config.yaml 中的 bench.data_dir)",
    )
    parser.add_argument(
        "--config", "-c", type=str, default="config.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="限制评估的条目数量（调试用）",
    )
    parser.add_argument(
        "--instruction-type", type=str, default=None,
        choices=["Cell-Level Manipulation", "Sheet-Level Manipulation"],
        help="按指令类型过滤",
    )
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help="并发数 (默认读取 config)",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=None,
        help="ReAct 最大轮次 (默认读取 config)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="指定 LLM 模型",
    )
    parser.add_argument(
        "--output-dir", "-o", type=str, default=None,
        help="结果输出目录",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细日志",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # 加载配置
    config = load_config(args.config)

    # 命令行参数覆盖配置
    if args.max_rounds:
        config.react.max_rounds = args.max_rounds
    if args.concurrency:
        config.bench.concurrency = args.concurrency

    data_dir = args.data_dir or config.bench.data_dir
    output_dir = args.output_dir or config.bench.output_dir

    # 检查数据目录
    if not Path(data_dir).exists():
        logger.error("数据目录不存在: %s", data_dir)
        sys.exit(1)

    # 初始化组件
    llm = LLMClient(config)
    renderer = SpreadsheetRenderer(backend=config.react.renderer_backend)
    executor = CodeExecutor(timeout=config.react.code_timeout)
    tracer = TraceRecorder(output_dir)
    react_agent = ReactAgent(llm, config.react, renderer, executor, tracer=tracer)
    comparator = SpreadsheetComparator()

    # 检查渲染后端
    if renderer.is_available():
        logger.info("渲染后端: %s (可用)", config.react.renderer_backend)
    else:
        logger.warning("LibreOffice 不可用，将使用文本回退模式")

    # 加载数据集
    dataset = BenchmarkDataset(data_dir)
    test_cases = dataset.expand_test_cases(
        limit=args.limit,
        instruction_type=args.instruction_type,
    )

    if not test_cases:
        logger.error("没有找到测试用例")
        sys.exit(1)

    # 运行评估
    runner = BenchmarkRunner(
        react_agent=react_agent,
        comparator=comparator,
        concurrency=config.bench.concurrency,
        retry=config.bench.retry,
    )

    result = await runner.run(test_cases)

    # 输出报告
    BenchmarkReporter.print_summary(result)
    BenchmarkReporter.save_results(result, output_dir)


if __name__ == "__main__":
    asyncio.run(main())
