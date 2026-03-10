"""MarkItDown 文档解析器"""

from __future__ import annotations

import os
from pathlib import Path

from markitdown import MarkItDown

from ..models import ParsedContent

# 后缀名 → 文件类型映射
_EXT_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
    ".pptx": "pptx",
    ".ppt": "ppt",
    ".docx": "docx",
    ".doc": "doc",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".xml": "xml",
}


class DocumentParser:
    """使用 MarkItDown 将文档统一转为 Markdown"""

    SUPPORTED = set(_EXT_MAP.values())

    def __init__(self):
        self.md = MarkItDown(enable_plugins=False)

    def parse(self, file_path: str) -> ParsedContent:
        """解析文档文件，返回统一的 ParsedContent"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_type = self._get_type(file_path)
        result = self.md.convert(file_path)

        stat = path.stat()
        metadata = {
            "file_name": path.name,
            "file_size": stat.st_size,
            "modified_time": stat.st_mtime,
        }

        return ParsedContent(
            source_path=str(path.resolve()),
            file_type=file_type,
            text_content=result.text_content,
            metadata=metadata,
        )

    @staticmethod
    def _get_type(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        return _EXT_MAP.get(ext, ext.lstrip("."))

    @classmethod
    def supports(cls, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in _EXT_MAP
