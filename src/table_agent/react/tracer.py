"""执行轨迹记录器 - 保存每轮截图、xlsx 快照和完整轨迹"""

from __future__ import annotations

import base64
import json
import logging
import shutil
from pathlib import Path

from .models import ReactResult

logger = logging.getLogger(__name__)


class TraceRecorder:
    """记录 ReAct agent 每轮执行轨迹到磁盘"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir) / "traces"

    def task_dir(self, task_id: str) -> Path:
        """返回并创建 traces/{task_id}/ 目录"""
        # task_id 可能含 # 等特殊字符，替换为安全字符
        safe_id = task_id.replace("#", "_").replace("/", "_")
        d = self.output_dir / safe_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_screenshots(
        self, task_id: str, round_num: int, screenshots: list[str]
    ) -> list[str]:
        """保存 base64 截图为 PNG 文件

        Args:
            task_id: 任务 ID
            round_num: 轮次号
            screenshots: base64 编码的 PNG 列表

        Returns:
            保存的文件路径列表
        """
        if not screenshots:
            return []

        d = self.task_dir(task_id)
        paths: list[str] = []

        for i, b64 in enumerate(screenshots):
            filename = f"round_{round_num}_sheet_{i}.png"
            filepath = d / filename
            filepath.write_bytes(base64.b64decode(b64))
            paths.append(str(filepath))

        logger.debug("保存 %d 张截图: %s round %d", len(paths), task_id, round_num)
        return paths

    def save_spreadsheet(
        self, task_id: str, round_num: int, xlsx_path: str
    ) -> str:
        """复制当前 xlsx 快照

        Args:
            task_id: 任务 ID
            round_num: 轮次号
            xlsx_path: 源 xlsx 文件路径

        Returns:
            保存的快照文件路径
        """
        d = self.task_dir(task_id)
        dest = d / f"round_{round_num}.xlsx"
        shutil.copy2(xlsx_path, dest)
        logger.debug("保存 xlsx 快照: %s", dest)
        return str(dest)

    def save_trace(self, result: ReactResult) -> str:
        """保存完整 ReactResult 为 JSON

        Args:
            result: 完整执行结果

        Returns:
            trace.json 文件路径
        """
        d = self.task_dir(result.task_id)
        trace_path = d / "trace.json"

        # 序列化时排除截图的 base64 内容（已保存为文件）
        data = result.model_dump()
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.debug("保存执行轨迹: %s", trace_path)
        return str(trace_path)
