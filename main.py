"""Table Agent CLI 入口"""

from __future__ import annotations

import asyncio
import argparse
import sys

from table_agent.agent import TableAgent
from table_agent.batch import BatchProcessor
from table_agent.skills.loader import SkillLoader
from table_agent.config import load_config


def cli():
    parser = argparse.ArgumentParser(
        description="Table Agent - 多格式文件语义处理框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  %(prog)s run invoice.pdf                     # 自动路由 skill 处理 PDF
  %(prog)s run data.xlsx --skill extract_table  # 指定 skill
  %(prog)s batch batch_tasks/clean_reports.yaml # 批量处理
  %(prog)s skills                              # 列出可用 skills
""",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # 单文件处理
    run_parser = subparsers.add_parser("run", help="处理单个文件")
    run_parser.add_argument("file", help="输入文件路径")
    run_parser.add_argument("--skill", help="指定 skill 名称 (不指定则自动路由)")
    run_parser.add_argument("--model", help="覆盖默认模型")
    run_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    # 批量处理
    batch_parser = subparsers.add_parser("batch", help="批量处理文件")
    batch_parser.add_argument("task", help="批量任务配置 YAML 路径")
    batch_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    # 列出可用 skills
    skills_parser = subparsers.add_parser("skills", help="列出所有可用 skills")
    skills_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    asyncio.run(_dispatch(args))


async def _dispatch(args):
    if args.command == "run":
        agent = TableAgent(config_path=args.config)
        result = await agent.process(
            args.file, skill_name=args.skill, model=args.model
        )
        print(result.model_dump_json(indent=2))

    elif args.command == "batch":
        agent = TableAgent(config_path=args.config)
        processor = BatchProcessor(agent)
        batch_result = await processor.run(args.task)
        print(f"\n{'='*40}")
        print(f"任务: {batch_result.task_name}")
        print(f"总计: {batch_result.total}")
        print(f"成功: {batch_result.success}")
        print(f"失败: {batch_result.failed}")
        if batch_result.errors:
            print("\n失败文件:")
            for err in batch_result.errors:
                print(f"  - {err['file']}: {err['error_message']}")

    elif args.command == "skills":
        config = load_config(args.config)
        loader = SkillLoader(config.skills_dir)
        metas = loader.load_metadata()
        if not metas:
            print("没有找到可用的 skills")
            return
        print(f"可用 Skills ({len(metas)}):\n")
        for meta in metas:
            print(f"  {meta.name}")
            print(f"    {meta.description}")
            print()


if __name__ == "__main__":
    cli()
