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
class ReactConfig:
    max_rounds: int = 5
    code_timeout: int = 30
    renderer_backend: str = "libreoffice"  # "libreoffice" | "text"


@dataclass
class BenchConfig:
    data_dir: str = "data/spreadsheetbench/all_data_912_v0.1"
    concurrency: int = 3
    retry: int = 1
    output_dir: str = "output/bench/"


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    react: ReactConfig = field(default_factory=ReactConfig)
    bench: BenchConfig = field(default_factory=BenchConfig)
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

    react_cfg = resolved.get("react", {})
    bench_cfg = resolved.get("bench", {})

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
        react=ReactConfig(
            max_rounds=react_cfg.get("max_rounds", 5),
            code_timeout=react_cfg.get("code_timeout", 30),
            renderer_backend=react_cfg.get("renderer_backend", "libreoffice"),
        ),
        bench=BenchConfig(
            data_dir=bench_cfg.get("data_dir", "data/spreadsheetbench/all_data_912_v0.1"),
            concurrency=bench_cfg.get("concurrency", 3),
            retry=bench_cfg.get("retry", 1),
            output_dir=bench_cfg.get("output_dir", "output/bench/"),
        ),
        skills_dir=resolved.get("skills_dir", "skills/"),
        output_dir=resolved.get("output_dir", "output/"),
        data_dir=resolved.get("data_dir", "data/"),
    )
