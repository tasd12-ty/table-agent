"""电子表格渲染器 - xlsx → PNG(base64)"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class SpreadsheetRenderer:
    """将 xlsx 文件渲染为 PNG 截图（base64 编码）"""

    def __init__(self, backend: str = "libreoffice"):
        self.backend = backend
        self._libreoffice_path = self._find_libreoffice()

    async def render(self, xlsx_path: str, sheet_name: str | None = None) -> list[str]:
        """渲染 xlsx 为 base64 PNG 列表（每个 sheet 一张）

        Args:
            xlsx_path: xlsx 文件路径
            sheet_name: 指定 sheet 名称，None 则渲染所有 sheet

        Returns:
            base64 编码的 PNG 图片列表
        """
        if self.backend == "libreoffice" and self._libreoffice_path:
            return await self._render_libreoffice(xlsx_path)
        return self._render_text_fallback(xlsx_path, sheet_name)

    async def _render_libreoffice(self, xlsx_path: str) -> list[str]:
        """LibreOffice 渲染：xlsx → pdf → png → base64"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # xlsx → pdf
            proc = await asyncio.create_subprocess_exec(
                self._libreoffice_path,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmp_dir,
                xlsx_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            pdf_files = list(Path(tmp_dir).glob("*.pdf"))
            if not pdf_files:
                logger.warning("LibreOffice 转换 PDF 失败，使用文本回退")
                return self._render_text_fallback(xlsx_path)

            # pdf → png (pypdfium2)
            return self._pdf_to_base64_images(pdf_files[0])

    @staticmethod
    def _pdf_to_base64_images(pdf_path: Path) -> list[str]:
        """使用 pypdfium2 将 PDF 页面渲染为 base64 PNG"""
        import pypdfium2 as pdfium

        images: list[str] = []
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            for i in range(len(pdf)):
                page = pdf[i]
                # 渲染为 2x 分辨率以保证清晰度
                bitmap = page.render(scale=2)
                pil_image = bitmap.to_pil()
                # PIL image → base64
                import io
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                images.append(b64)
        finally:
            pdf.close()
        return images

    @staticmethod
    def _render_text_fallback(xlsx_path: str, sheet_name: str | None = None) -> list[str]:
        """文本回退：openpyxl 读取单元格值，格式化为文本表格图片

        在无 LibreOffice 环境下使用。返回文本内容编码为 base64 的简单图片。
        实际上返回空列表，让 agent 仅依赖 text_content。
        """
        import openpyxl

        wb = openpyxl.load_workbook(xlsx_path, data_only=True)
        sheets = [wb[sheet_name]] if sheet_name and sheet_name in wb.sheetnames else wb.worksheets

        # 文本回退不生成图片，返回空列表
        # agent 将依赖 openpyxl 读取的文本数据进行推理
        logger.info("使用文本回退模式，不生成截图（共 %d 个 sheet）", len(sheets))
        wb.close()
        return []

    @staticmethod
    def _find_libreoffice() -> str | None:
        """查找系统中的 LibreOffice 可执行文件"""
        # macOS 常见路径
        mac_path = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if Path(mac_path).exists():
            return mac_path

        # PATH 中查找
        path = shutil.which("libreoffice") or shutil.which("soffice")
        if path:
            return path

        logger.warning("未找到 LibreOffice，将使用文本回退模式")
        return None

    def is_available(self) -> bool:
        """检查渲染后端是否可用"""
        if self.backend == "libreoffice":
            return self._libreoffice_path is not None
        return True
