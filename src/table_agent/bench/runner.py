"""评估编排器 - 运行 ReAct agent 并对比结果"""

from __future__ import annotations

import asyncio
import logging
import time

from ..react.agent import ReactAgent
from .comparator import SpreadsheetComparator
from .models import BenchmarkResult, ComparisonResult, TestCase, TestCaseResult

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """SpreadsheetBench 评估运行器"""

    def __init__(
        self,
        react_agent: ReactAgent,
        comparator: SpreadsheetComparator | None = None,
        concurrency: int = 3,
        retry: int = 1,
    ):
        self.react_agent = react_agent
        self.comparator = comparator or SpreadsheetComparator()
        self.concurrency = concurrency
        self.retry = retry

    async def run(self, test_cases: list[TestCase]) -> BenchmarkResult:
        """运行评估

        Args:
            test_cases: 测试用例列表

        Returns:
            BenchmarkResult 汇总结果
        """
        sem = asyncio.Semaphore(self.concurrency)
        results: list[TestCaseResult] = []
        errors: list[dict] = []

        async def _process(tc: TestCase) -> None:
            async with sem:
                try:
                    result = await self._run_one(tc)
                    results.append(result)
                    logger.info(
                        "完成 %s#%d: accuracy=%.2f",
                        tc.entry_id,
                        tc.test_num,
                        result.comparison.accuracy,
                    )
                except Exception as e:
                    logger.error("失败 %s#%d: %s", tc.entry_id, tc.test_num, e)
                    errors.append({
                        "entry_id": tc.entry_id,
                        "test_num": tc.test_num,
                        "error": str(e),
                    })

        logger.info("开始评估: %d 个测试用例, 并发=%d", len(test_cases), self.concurrency)
        await asyncio.gather(*[_process(tc) for tc in test_cases])

        return self._aggregate(results, errors, test_cases)

    async def _run_one(self, tc: TestCase) -> TestCaseResult:
        """运行单个测试用例（含重试）"""
        last_error: Exception | None = None

        for attempt in range(1, self.retry + 1):
            try:
                start = time.time()

                # 运行 ReAct agent
                react_result = await self.react_agent.run(
                    instruction=tc.instruction,
                    input_xlsx=tc.input_path,
                    answer_sheet=tc.answer_sheet,
                    data_position=tc.data_position,
                    task_id=f"{tc.entry_id}#{tc.test_num}",
                )

                # 对比结果
                if react_result.output_file:
                    comparison = self.comparator.compare(
                        output_path=react_result.output_file,
                        answer_path=tc.answer_path,
                        answer_position=tc.answer_position,
                        answer_sheet=tc.answer_sheet,
                    )
                else:
                    comparison = ComparisonResult(
                        error="agent 未生成输出文件",
                    )

                elapsed = time.time() - start

                return TestCaseResult(
                    entry_id=tc.entry_id,
                    test_num=tc.test_num,
                    instruction_type=tc.instruction_type,
                    react_result=react_result,
                    comparison=comparison,
                    elapsed_seconds=elapsed,
                )

            except Exception as e:
                last_error = e
                if attempt < self.retry:
                    logger.warning(
                        "重试 %s#%d (第 %d 次): %s",
                        tc.entry_id, tc.test_num, attempt, e,
                    )

        raise last_error  # type: ignore[misc]

    @staticmethod
    def _aggregate(
        results: list[TestCaseResult],
        errors: list[dict],
        test_cases: list[TestCase],
    ) -> BenchmarkResult:
        """汇总所有结果"""
        cell_level = [
            r for r in results
            if r.instruction_type == "Cell-Level Manipulation"
        ]
        sheet_level = [
            r for r in results
            if r.instruction_type == "Sheet-Level Manipulation"
        ]

        def avg_accuracy(rs: list[TestCaseResult]) -> float:
            if not rs:
                return 0.0
            return sum(r.comparison.accuracy for r in rs) / len(rs)

        from datetime import datetime, timezone

        return BenchmarkResult(
            total_cases=len(test_cases),
            completed=len(results),
            failed=len(errors),
            cell_level_accuracy=avg_accuracy(cell_level),
            sheet_level_accuracy=avg_accuracy(sheet_level),
            overall_accuracy=avg_accuracy(results),
            per_task_results=results,
            errors=errors,
            model_used=results[0].react_result.model_used if results else "",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
