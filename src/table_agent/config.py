"""配置加载"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "http://localhost:8000/v1"
    default_model: str = "Qwen/Qwen3-8B"
    router_model: str = "Qwen/Qwen3-8B"


@dataclass
class VideoConfig:
    max_frames: int = 10
    frame_interval_sec: float = 2.0


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    skills_dir: str = "skills/"
    output_dir: str = "output/"
    data_dir: str = "data/"


def _resolve_env_vars(value: str) -> str:
    """替换 ${ENV_VAR} 为环境变量值"""
    pattern = re.compile(r"\$\{(\w+)\}")

    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return pattern.sub(replacer, value)


def _resolve_dict(d: dict) -> dict:
    """递归替换字典中的环境变量"""
    resolved = {}
    for k, v in d.items():
        if isinstance(v, str):
            resolved[k] = _resolve_env_vars(v)
        elif isinstance(v, dict):
            resolved[k] = _resolve_dict(v)
        else:
            resolved[k] = v
    return resolved


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """加载配置文件并替换环境变量"""
    path = Path(config_path)
    if not path.exists():
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    resolved = _resolve_dict(raw)

    # 兼容旧版 "openrouter" 配置名
    llm_cfg = resolved.get("llm") or resolved.get("openrouter", {})
    video_cfg = resolved.get("video", {})

    return AppConfig(
        llm=LLMConfig(
            api_key=llm_cfg.get("api_key", ""),
            base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
            default_model=llm_cfg.get("default_model", "Qwen/Qwen3-8B"),
            router_model=llm_cfg.get("router_model", "Qwen/Qwen3-8B"),
        ),
        video=VideoConfig(
            max_frames=video_cfg.get("max_frames", 10),
            frame_interval_sec=video_cfg.get("frame_interval_sec", 2.0),
        ),
        skills_dir=resolved.get("skills_dir", "skills/"),
        output_dir=resolved.get("output_dir", "output/"),
        data_dir=resolved.get("data_dir", "data/"),
    )
