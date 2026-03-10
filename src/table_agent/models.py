"""数据模型定义"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class ParsedContent(BaseModel):
    """文件解析后的统一内容表示"""

    source_path: str
    file_type: str  # pdf, xlsx, csv, pptx, docx, mp4, ...
    text_content: str | None = None  # Markdown 文本 (文档类)
    images: list[str] = Field(default_factory=list)  # base64 编码图片 (视频帧)
    metadata: dict = Field(default_factory=dict)  # 文件元信息

    def summary(self, max_chars: int = 500) -> str:
        """返回内容摘要，用于 skill 路由"""
        parts: list[str] = [f"[文件类型: {self.file_type}] {self.source_path}"]
        if self.text_content:
            parts.append(self.text_content[:max_chars])
        if self.images:
            parts.append(f"[包含 {len(self.images)} 张图片]")
        if self.metadata:
            parts.append(f"[元信息: {self.metadata}]")
        return "\n".join(parts)


class SkillMeta(BaseModel):
    """轻量元数据，用于渐进式披露第一阶段"""

    name: str
    description: str
    skill_dir: Path


class SkillConfig(SkillMeta):
    """完整 skill 配置，第二阶段加载"""

    full_content: str = ""  # SKILL.md 完整 markdown 内容
    input_types: list[str] = Field(default_factory=list)
    output_format: str = "json"


class AgentResult(BaseModel):
    """Agent 处理结果"""

    skill_name: str
    input_file: str
    output: dict | str  # LLM 返回的结构化结果
    model_used: str
    raw_response: str = ""  # 原始 LLM 响应
    metadata: dict = Field(default_factory=dict)


class BatchTaskConfig(BaseModel):
    """批量任务配置"""

    name: str
    description: str = ""
    input_paths: list[str]
    skill: str | None = None
    model: str | None = None
    concurrency: int = 5
    retry: int = 2
    output_dir: str = "./output"
    output_format: str = "jsonl"  # json | jsonl | csv


class BatchResult(BaseModel):
    """批量处理结果"""

    task_name: str
    total: int
    success: int
    failed: int
    results: list[AgentResult] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)  # {file, error_message}
