"""Agent 编排器 - 主 pipeline"""

from __future__ import annotations

import os
from pathlib import Path

from .config import AppConfig, load_config
from .llm import LLMClient
from .models import AgentResult, ParsedContent
from .parsers.document import DocumentParser
from .parsers.video import VideoParser
from .skills.executor import SkillExecutor
from .skills.loader import SkillLoader
from .skills.router import SkillRouter


class TableAgent:
    """Table Agent 主编排器

    Pipeline:
        文件输入 → 解析 → skill 路由 → skill 执行 → 结构化输出
    """

    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        self.llm = LLMClient(self.config)
        self.doc_parser = DocumentParser()
        self.video_parser = VideoParser(
            max_frames=self.config.video.max_frames,
            interval_sec=self.config.video.frame_interval_sec,
        )
        self.skill_loader = SkillLoader(self.config.skills_dir)
        self.skill_router = SkillRouter(self.llm, self.skill_loader, self.config)
        self.skill_executor = SkillExecutor(self.llm)

    async def process(
        self,
        file_path: str,
        skill_name: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        """主 pipeline

        Args:
            file_path: 输入文件路径
            skill_name: 指定 skill 名称 (不指定则自动路由)
            model: 覆盖默认模型

        Returns:
            AgentResult 结构化结果
        """
        # 1. 检测文件类型
        file_type = self._detect_file_type(file_path)

        # 2. 解析文件
        content = self._parse(file_path, file_type)

        # 3. 选择 skill
        if skill_name:
            skill = self.skill_loader.load_full(skill_name)
        else:
            skill = await self.skill_router.route(content)

        # 4. 执行 skill
        result = await self.skill_executor.execute(skill, content, model=model)

        return result

    def _parse(self, file_path: str, file_type: str) -> ParsedContent:
        """根据文件类型选择解析器"""
        if VideoParser.supports(file_path):
            return self.video_parser.parse(file_path)
        elif DocumentParser.supports(file_path):
            return self.doc_parser.parse(file_path)
        else:
            # fallback: 尝试用 MarkItDown 解析
            return self.doc_parser.parse(file_path)

    @staticmethod
    def _detect_file_type(file_path: str) -> str:
        """根据后缀名检测文件类型"""
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if not ext:
            raise ValueError(f"无法检测文件类型: {file_path}")
        return ext
