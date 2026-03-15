"""ReAct agent 数据模型"""

from __future__ import annotations

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """代码执行结果"""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False


class ReactStep(BaseModel):
    """单轮 ReAct 步骤"""

    round: int
    thought: str
    code: str | None = None
    action: str  # "code" | "done"
    execution_result: ExecutionResult | None = None
    raw_response: str = ""  # LLM 原始响应
    screenshot_paths: list[str] = []  # 截图文件路径
    spreadsheet_path: str = ""  # 本轮 xlsx 快照路径


class ReactResult(BaseModel):
    """ReAct agent 完整执行结果"""

    task_id: str
    instruction: str
    input_file: str
    output_file: str | None = None
    steps: list[ReactStep] = []
    total_rounds: int = 0
    success: bool = False
    error_message: str = ""
    model_used: str = ""
