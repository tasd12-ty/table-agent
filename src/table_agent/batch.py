"""批量处理引擎"""

from __future__ import annotations

import asyncio
import csv
import glob
import json
import traceback
from pathlib import Path

import yaml

from .agent import TableAgent
from .models import AgentResult, BatchResult, BatchTaskConfig


class BatchProcessor:
    """批量处理引擎

    支持:
    - YAML 配置批量任务
    - 并发控制 (asyncio.Semaphore)
    - 失败重试
    - 多格式输出 (json / jsonl / csv)
    """

    def __init__(self, agent: TableAgent):
        self.agent = agent

    async def run(self, task_config_path: str) -> BatchResult:
        """执行批量任务

        Args:
            task_config_path: 批量任务 YAML 配置文件路径

        Returns:
            BatchResult 批量结果
        """
        config = self._load_task_config(task_config_path)
        files = self._expand_paths(config.input_paths)

        if not files:
            return BatchResult(
                task_name=config.name,
                total=0,
                success=0,
                failed=0,
            )

        print(f"[batch] 任务: {config.name}")
        print(f"[batch] 文件数: {len(files)}, 并发: {config.concurrency}")

        semaphore = asyncio.Semaphore(config.concurrency)
        results: list[AgentResult] = []
        errors: list[dict] = []

        async def _bounded_process(fp: str):
            async with semaphore:
                return await self._process_one(fp, config)

        tasks = [_bounded_process(fp) for fp in files]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for file_path, outcome in zip(files, outcomes):
            if isinstance(outcome, Exception):
                errors.append({
                    "file": file_path,
                    "error_message": str(outcome),
                })
            elif outcome is None:
                errors.append({
                    "file": file_path,
                    "error_message": "处理返回空结果",
                })
            else:
                results.append(outcome)

        batch_result = BatchResult(
            task_name=config.name,
            total=len(files),
            success=len(results),
            failed=len(errors),
            results=results,
            errors=errors,
        )

        # 保存结果
        self._save_results(results, config)

        return batch_result

    async def _process_one(
        self, file_path: str, config: BatchTaskConfig
    ) -> AgentResult | None:
        """处理单个文件，带重试"""
        last_error: Exception | None = None

        for attempt in range(1 + config.retry):
            try:
                result = await self.agent.process(
                    file_path=file_path,
                    skill_name=config.skill,
                    model=config.model,
                )
                print(f"  [ok] {file_path}")
                return result
            except Exception as e:
                last_error = e
                if attempt < config.retry:
                    print(f"  [retry {attempt + 1}] {file_path}: {e}")

        print(f"  [fail] {file_path}: {last_error}")
        raise last_error  # type: ignore

    def _save_results(self, results: list[AgentResult], config: BatchTaskConfig):
        """按配置格式保存结果"""
        if not results:
            return

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if config.output_format == "jsonl":
            output_file = output_dir / f"{config.name}.jsonl"
            with open(output_file, "w", encoding="utf-8") as f:
                for r in results:
                    f.write(r.model_dump_json() + "\n")

        elif config.output_format == "json":
            output_file = output_dir / f"{config.name}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(
                    [r.model_dump() for r in results],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        elif config.output_format == "csv":
            output_file = output_dir / f"{config.name}.csv"
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["skill_name", "input_file", "output", "model_used"],
                )
                writer.writeheader()
                for r in results:
                    writer.writerow({
                        "skill_name": r.skill_name,
                        "input_file": r.input_file,
                        "output": json.dumps(r.output, ensure_ascii=False)
                        if isinstance(r.output, dict)
                        else r.output,
                        "model_used": r.model_used,
                    })

        print(f"[batch] 结果已保存: {output_file}")

    @staticmethod
    def _load_task_config(path: str) -> BatchTaskConfig:
        """加载批量任务 YAML 配置"""
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        input_cfg = raw.get("input", {})
        processing = raw.get("processing", {})
        output = raw.get("output", {})

        return BatchTaskConfig(
            name=raw.get("name", "unnamed_batch"),
            description=raw.get("description", ""),
            input_paths=input_cfg.get("paths", []),
            skill=processing.get("skill"),
            model=processing.get("model"),
            concurrency=processing.get("concurrency", 5),
            retry=processing.get("retry", 2),
            output_dir=output.get("directory", "./output"),
            output_format=output.get("format", "jsonl"),
        )

    @staticmethod
    def _expand_paths(patterns: list[str]) -> list[str]:
        """展开 glob 模式为文件列表"""
        files: list[str] = []
        for pattern in patterns:
            matched = glob.glob(pattern, recursive=True)
            files.extend(sorted(matched))
        return files
