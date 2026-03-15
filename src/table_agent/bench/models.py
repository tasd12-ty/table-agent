"""SpreadsheetBench 评估数据模型"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from ..react.models import ReactResult


class BenchmarkEntry(BaseModel):
    """dataset.json 中的单条记录"""

    id: str
    instruction: str
    spreadsheet_path: str
    instruction_type: str  # "Cell-Level Manipulation" | "Sheet-Level Manipulation"
    answer_position: str
    answer_sheet: str = ""       # Cell-Level 任务可能缺失
    data_position: str = ""      # Cell-Level 任务可能缺失

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)


class TestCase(BaseModel):
    """展开后的单个测试用例（一对 input/answer 文件）"""

    entry_id: str
    test_num: int
    input_path: str
    answer_path: str
    instruction: str
    instruction_type: str
    answer_position: str
    answer_sheet: str = ""
    data_position: str = ""


class CellRange(BaseModel):
    """解析后的单元格范围"""

    sheet: str
    start_cell: str
    end_cell: str | None = None


class ComparisonResult(BaseModel):
    """单个测试用例的对比结果"""

    entry_id: str = ""
    test_num: int = 0
    total_cells: int = 0
    matched_cells: int = 0
    accuracy: float = 0.0
    mismatches: list[dict] = []
    error: str | None = None


class TestCaseResult(BaseModel):
    """单个测试用例的完整结果"""

    entry_id: str
    test_num: int
    instruction_type: str
    react_result: ReactResult
    comparison: ComparisonResult
    elapsed_seconds: float = 0.0


class BenchmarkResult(BaseModel):
    """汇总评估结果"""

    total_cases: int = 0
    completed: int = 0
    failed: int = 0
    cell_level_accuracy: float = 0.0
    sheet_level_accuracy: float = 0.0
    overall_accuracy: float = 0.0
    per_task_results: list[TestCaseResult] = []
    errors: list[dict] = []
    model_used: str = ""
    timestamp: str = ""
