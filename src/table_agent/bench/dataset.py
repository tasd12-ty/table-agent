"""SpreadsheetBench 数据集加载器"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import BenchmarkEntry, TestCase

logger = logging.getLogger(__name__)


class BenchmarkDataset:
    """加载和管理 SpreadsheetBench 数据集"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.dataset_json = self.data_dir / "dataset.json"

    def load(self) -> list[BenchmarkEntry]:
        """从 dataset.json 加载所有条目"""
        if not self.dataset_json.exists():
            raise FileNotFoundError(f"数据集文件不存在: {self.dataset_json}")

        with open(self.dataset_json, encoding="utf-8") as f:
            raw = json.load(f)

        entries = [BenchmarkEntry(**item) for item in raw]
        logger.info("加载 %d 条 benchmark 条目", len(entries))
        return entries

    def expand_test_cases(
        self,
        entries: list[BenchmarkEntry] | None = None,
        limit: int | None = None,
        instruction_type: str | None = None,
    ) -> list[TestCase]:
        """将 BenchmarkEntry 展开为 TestCase 列表

        每个 entry 有 1-3 个测试用例（input/answer 对）。

        Args:
            entries: 条目列表，None 则重新加载
            limit: 限制条目数量（非测试用例数量）
            instruction_type: 按类型过滤 ("Cell-Level Manipulation" | "Sheet-Level Manipulation")

        Returns:
            展开后的 TestCase 列表
        """
        if entries is None:
            entries = self.load()

        if instruction_type:
            entries = [e for e in entries if e.instruction_type == instruction_type]

        if limit:
            entries = entries[:limit]

        test_cases: list[TestCase] = []
        for entry in entries:
            file_pairs = self._find_test_files(entry)
            for test_num, (input_path, answer_path) in enumerate(file_pairs, 1):
                test_cases.append(TestCase(
                    entry_id=entry.id,
                    test_num=test_num,
                    input_path=input_path,
                    answer_path=answer_path,
                    instruction=entry.instruction,
                    instruction_type=entry.instruction_type,
                    answer_position=entry.answer_position,
                    answer_sheet=entry.answer_sheet,
                    data_position=entry.data_position,
                ))

        logger.info(
            "展开 %d 条 entry → %d 个测试用例",
            len(entries),
            len(test_cases),
        )
        return test_cases

    def _find_test_files(self, entry: BenchmarkEntry) -> list[tuple[str, str]]:
        """查找一个 entry 下的所有 (input, answer) 文件对

        文件命名: {N}_{id}_input.xlsx, {N}_{id}_answer.xlsx
        """
        spreadsheet_dir = self.data_dir / entry.spreadsheet_path
        if not spreadsheet_dir.exists():
            logger.warning("目录不存在: %s", spreadsheet_dir)
            return []

        pairs: list[tuple[str, str]] = []
        # 收集所有 input 文件
        input_files = sorted(spreadsheet_dir.glob(f"*_{entry.id}_input.*"))

        for input_file in input_files:
            # 从 input 文件名推断 answer 文件名
            answer_name = input_file.name.replace("_input.", "_answer.")
            answer_file = input_file.parent / answer_name
            if answer_file.exists():
                pairs.append((str(input_file), str(answer_file)))
            else:
                logger.warning("缺少 answer 文件: %s", answer_name)

        return pairs
