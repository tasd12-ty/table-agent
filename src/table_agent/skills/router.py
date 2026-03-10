"""渐进式 Skill 路由 - LLM tool calling 决策"""

from __future__ import annotations

import json

from ..config import AppConfig
from ..llm import LLMClient
from ..models import ParsedContent, SkillConfig, SkillMeta
from .loader import SkillLoader

# 路由系统提示词 (框架内置，可后续调整)
_ROUTER_SYSTEM_PROMPT = """你是一个智能路由器。根据用户提供的文件内容摘要，选择最合适的处理技能(skill)。
通过调用对应的 skill function 来表示你的选择。"""


class SkillRouter:
    """渐进式披露 + LLM tool calling 路由

    流程:
    1. 加载所有 skill 轻量元数据 (name + description)
    2. 将 skills 转为 OpenAI function calling tools 格式
    3. 将 ParsedContent 摘要发给 LLM
    4. LLM 通过 tool calling 选择最合适的 skill
    5. 加载选中 skill 的完整 SKILL.md
    """

    def __init__(self, llm: LLMClient, skill_loader: SkillLoader, config: AppConfig):
        self.llm = llm
        self.skill_loader = skill_loader
        self.router_model = config.openrouter.router_model

    def _skills_to_tools(self, skills: list[SkillMeta]) -> list[dict]:
        """将 skill 元数据转为 OpenAI function calling tools 格式"""
        tools = []
        for skill in skills:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": skill.name,
                        "description": skill.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "reason": {
                                    "type": "string",
                                    "description": "选择此 skill 的原因",
                                },
                            },
                            "required": ["reason"],
                        },
                    },
                }
            )
        return tools

    async def route(self, content: ParsedContent) -> SkillConfig:
        """根据内容自动选择 skill

        Returns:
            完整加载的 SkillConfig
        """
        # 1. 加载轻量元数据
        skills = self.skill_loader.load_metadata()
        if not skills:
            raise ValueError("没有可用的 skill")

        if len(skills) == 1:
            # 只有一个 skill，直接返回
            return self.skill_loader.load_full(skills[0].name)

        # 2. 转为 tools
        tools = self._skills_to_tools(skills)

        # 3. 构建路由消息
        messages = [
            {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": content.summary()},
        ]

        # 4. 调 LLM with tools
        result = await self.llm.chat_with_tools(
            messages=messages,
            tools=tools,
            model=self.router_model,
        )

        # 5. 解析选择
        tool_calls = result.get("tool_calls")
        if tool_calls and len(tool_calls) > 0:
            selected_name = tool_calls[0].function.name
            return self.skill_loader.load_full(selected_name)

        # fallback: 如果 LLM 没有调用 tool，使用第一个 skill
        return self.skill_loader.load_full(skills[0].name)
