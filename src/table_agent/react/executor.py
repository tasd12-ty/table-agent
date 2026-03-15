"""代码执行器 - subprocess 沙箱"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from .models import ExecutionResult

logger = logging.getLogger(__name__)


class CodeExecutor:
    """在 subprocess 中执行 LLM 生成的 Python 代码"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def execute(self, code: str, work_dir: str) -> ExecutionResult:
        """执行 Python 代码

        Args:
            code: Python 代码字符串
            work_dir: 工作目录（包含 input.xlsx）

        Returns:
            ExecutionResult
        """
        script_path = Path(work_dir) / "_agent_script.py"
        script_path.write_text(code, encoding="utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", str(script_path),
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                logger.warning("代码执行超时 (%ds)", self.timeout)
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"执行超时（{self.timeout}秒）",
                    return_code=-1,
                    timed_out=True,
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            success = proc.returncode == 0

            if not success:
                logger.debug("代码执行失败 (rc=%d): %s", proc.returncode, stderr[:200])

            return ExecutionResult(
                success=success,
                stdout=stdout,
                stderr=stderr,
                return_code=proc.returncode or 0,
                timed_out=False,
            )

        except Exception as e:
            logger.error("代码执行异常: %s", e)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                timed_out=False,
            )
        finally:
            # 清理脚本文件
            script_path.unlink(missing_ok=True)
