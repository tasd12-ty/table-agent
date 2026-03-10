"""Table Agent 使用示例"""

import asyncio
from table_agent.agent import TableAgent
from table_agent.batch import BatchProcessor


async def single_file_example():
    """单文件处理示例"""
    agent = TableAgent(config_path="config.yaml")

    # 自动路由 skill
    result = await agent.process("path/to/document.pdf")
    print(result.model_dump_json(indent=2))

    # 指定 skill
    result = await agent.process("path/to/data.xlsx", skill_name="extract_table")
    print(result.model_dump_json(indent=2))

    # 覆盖模型
    result = await agent.process(
        "path/to/video.mp4",
        model="anthropic/claude-sonnet-4",
    )
    print(result.model_dump_json(indent=2))


async def batch_example():
    """批量处理示例"""
    agent = TableAgent(config_path="config.yaml")
    processor = BatchProcessor(agent)

    batch_result = await processor.run("batch_tasks/example_batch.yaml")
    print(f"成功: {batch_result.success}/{batch_result.total}")


async def programmatic_batch():
    """编程方式批量处理 (不使用 YAML 配置)"""
    agent = TableAgent(config_path="config.yaml")

    files = [
        "data/report_q1.pdf",
        "data/report_q2.pdf",
        "data/financial.xlsx",
    ]

    results = await asyncio.gather(
        *[agent.process(f, skill_name="extract_table") for f in files],
        return_exceptions=True,
    )

    for file_path, result in zip(files, results):
        if isinstance(result, Exception):
            print(f"[FAIL] {file_path}: {result}")
        else:
            print(f"[OK] {file_path}: {result.skill_name}")


if __name__ == "__main__":
    asyncio.run(single_file_example())
