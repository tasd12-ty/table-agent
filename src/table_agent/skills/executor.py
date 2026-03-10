"""Skill 执行器 - 构建 prompt 并调用 LLM"""

from __future__ import annotations

import json
import re

from ..llm import LLMClient
from ..models import AgentResult, ParsedContent, SkillConfig


class SkillExecutor:
    """执行选中的 skill：提取 prompt 模板，填充内容，调用 LLM"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def execute(
        self,
        skill: SkillConfig,
        content: ParsedContent,
        model: str | None = None,
    ) -> AgentResult:
        """执行 skill

        1. 从 SKILL.md 内容中提取 system_prompt, user_prompt_template
        2. 用 content 填充 prompt
        3. 根据 content 类型选择 chat 或 chat_with_images
        4. 返回 AgentResult
        """
        system_prompt = self._extract_section(skill.full_content, "System Prompt")
        user_template = self._extract_section(skill.full_content, "User Prompt Template")

        # 填充 user prompt
        user_prompt = self._fill_template(user_template, content)

        used_model = model or self.llm.default_model

        # 根据内容类型选择调用方式
        if content.images:
            raw_response = await self.llm.chat_with_images(
                text=user_prompt,
                images=content.images,
                model=used_model,
                system_prompt=system_prompt or None,
            )
        else:
            messages: list[dict] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})

            raw_response = await self.llm.chat(
                messages=messages,
                model=used_model,
            )

        # 尝试解析 JSON 输出
        output = self._try_parse_json(raw_response)

        return AgentResult(
            skill_name=skill.name,
            input_file=content.source_path,
            output=output,
            model_used=used_model,
            raw_response=raw_response,
            metadata={"file_type": content.file_type},
        )

    @staticmethod
    def _extract_section(markdown: str, section_name: str) -> str:
        """从 markdown 中提取指定 ## 标题下的内容"""
        pattern = rf"##\s+{re.escape(section_name)}\s*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, markdown, re.DOTALL)
        if match:
            content = match.group(1).strip()
            # 移除 HTML 注释 (<!-- TODO -->)
            content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
            return content
        return ""

    @staticmethod
    def _fill_template(template: str, content: ParsedContent) -> str:
        """用 ParsedContent 填充 prompt 模板

        支持的占位符:
        - {text_content}: 文件的 Markdown 文本
        - {file_type}: 文件类型
        - {source_path}: 源文件路径
        - {metadata}: 元信息 JSON
        """
        if not template:
            # 无模板时使用默认格式
            return content.summary()

        replacements = {
            "{text_content}": content.text_content or "",
            "{file_type}": content.file_type,
            "{source_path}": content.source_path,
            "{metadata}": json.dumps(content.metadata, ensure_ascii=False),
        }
        result = template
        for key, value in replacements.items():
            result = result.replace(key, value)
        return result

    @staticmethod
    def _try_parse_json(text: str) -> dict | str:
        """尝试将 LLM 响应解析为 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return text
