"""OpenRouter LLM 客户端"""

from __future__ import annotations

import openai

from .config import AppConfig


class LLMClient:
    """基于 openai SDK 的 OpenRouter LLM 客户端"""

    def __init__(self, config: AppConfig):
        self.client = openai.AsyncOpenAI(
            base_url=config.openrouter.base_url,
            api_key=config.openrouter.api_key,
        )
        self.default_model = config.openrouter.default_model

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """文本对话"""
        kwargs: dict = {
            "model": model or self.default_model,
            "messages": messages,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def chat_with_images(
        self,
        text: str,
        images: list[str],
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """多模态对话，images 为 base64 列表"""
        content: list[dict] = [{"type": "text", "text": text}]
        for img_b64 in images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                }
            )

        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        response = await self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
    ) -> dict:
        """带 tool calling 的对话，用于 skill 路由

        返回:
            {
                "tool_calls": [...] | None,
                "content": str | None,
                "message": <完整 message 对象>
            }
        """
        response = await self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            tools=tools,
        )
        msg = response.choices[0].message
        return {
            "tool_calls": msg.tool_calls,
            "content": msg.content,
            "message": msg,
        }
