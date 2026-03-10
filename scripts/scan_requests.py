"""批量扫描 request 目录，对每个 request 做质量评估和任务类型分析。

用法:
    uv run python scripts/scan_requests.py /path/to/data_dir \
        --concurrency 5 \
        --output results.jsonl \
        --config config.yaml \
        --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# 将项目根目录加入 sys.path 以便导入 table_agent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from markitdown import MarkItDown

from table_agent.config import load_config
from table_agent.llm import LLMClient
from table_agent.models import RequestScanResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """\
你是一个数据清洗任务质量评估专家。你将收到一个数据清洗 request 的完整信息，包括：
- 用户的原始需求描述
- 输入文件列表
- 输出文件内容
- 执行代码

请分析并返回 JSON 格式的评估结果。

评估维度：
1. **任务类型分析**：根据需求描述和输入/输出判断任务类型
2. **质量评估**：对比需求 vs 实际输出，评估完成质量

返回 JSON 格式（不要包含 markdown code fence）：
{
    "task_type": "数据清洗|格式转换|统计分析|可视化|数据合并|数据筛选|其他",
    "task_tags": ["tag1", "tag2"],
    "quality_score": 0.85,
    "quality_notes": "简要说明质量评估理由"
}

评分标准：
- 1.0: 完美完成，输出完全符合需求
- 0.8-0.9: 基本完成，有小瑕疵
- 0.6-0.7: 部分完成，有明显遗漏
- 0.4-0.5: 完成度不足
- 0.0-0.3: 未完成或结果错误
"""


def _format_context(
    request_txt: str,
    input_files: list[str],
    output_content: str,
    code_content: str,
) -> str:
    """将所有上下文组装为 user prompt."""
    parts = [
        "## 用户需求\n",
        request_txt.strip(),
        "\n\n## 输入文件\n",
        "\n".join(f"- {f}" for f in input_files) if input_files else "(无输入文件)",
        "\n\n## 输出内容\n",
        output_content.strip() if output_content.strip() else "(无输出内容)",
        "\n\n## 执行代码\n",
        code_content.strip() if code_content.strip() else "(无代码)",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 文件读取工具
# ---------------------------------------------------------------------------

def read_request_txt(request_dir: Path) -> str:
    """读取 request/{request_id}_request.txt"""
    request_subdir = request_dir / "request"
    if not request_subdir.exists():
        return ""
    for f in request_subdir.iterdir():
        if f.suffix == ".txt":
            return f.read_text(encoding="utf-8", errors="replace")
    return ""


def list_input_files(request_dir: Path) -> list[str]:
    """列出 input/ 下所有文件名"""
    input_dir = request_dir / "input"
    if not input_dir.exists():
        return []
    return sorted(f.name for f in input_dir.iterdir() if f.is_file())


def parse_outputs(request_dir: Path, md: MarkItDown) -> str:
    """读取 output/ 下所有文件内容，使用 MarkItDown 转换"""
    output_dir = request_dir / "output"
    if not output_dir.exists():
        return ""
    parts: list[str] = []
    for f in sorted(output_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix == ".txt":
            content = f.read_text(encoding="utf-8", errors="replace")
            parts.append(f"### {f.name}\n{content}")
        else:
            try:
                result = md.convert(str(f))
                parts.append(f"### {f.name}\n{result.text_content}")
            except Exception as e:
                parts.append(f"### {f.name}\n(解析失败: {e})")
    return "\n\n".join(parts)


def list_output_files(request_dir: Path) -> list[str]:
    """列出 output/ 下所有文件名"""
    output_dir = request_dir / "output"
    if not output_dir.exists():
        return []
    return sorted(f.name for f in output_dir.iterdir() if f.is_file())


def read_code(request_dir: Path) -> str:
    """读取 code/ 下的 Python 脚本"""
    code_dir = request_dir / "code"
    if not code_dir.exists():
        return ""
    parts: list[str] = []
    for f in sorted(code_dir.iterdir()):
        if f.is_file() and f.suffix == ".py":
            content = f.read_text(encoding="utf-8", errors="replace")
            parts.append(f"### {f.name}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def _parse_llm_json(text: str) -> dict:
    """从 LLM 响应中解析 JSON，容忍 markdown code fence."""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首尾 code fence
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


# ---------------------------------------------------------------------------
# 核心扫描逻辑
# ---------------------------------------------------------------------------

async def scan_request(
    request_dir: Path,
    llm: LLMClient,
    md: MarkItDown,
    model: str | None = None,
) -> RequestScanResult:
    """扫描单个 request 目录，返回结构化结果."""
    request_id = request_dir.name

    request_txt = read_request_txt(request_dir)
    input_files = list_input_files(request_dir)
    output_files = list_output_files(request_dir)
    output_content = parse_outputs(request_dir, md)
    code_content = read_code(request_dir)
    has_code = bool(code_content.strip())

    user_prompt = _format_context(request_txt, input_files, output_content, code_content)

    # 调 LLM 分析
    response = await llm.chat(
        messages=[
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        response_format={"type": "json_object"},
    )

    try:
        analysis = _parse_llm_json(response)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("request %s: JSON 解析失败: %s", request_id, e)
        analysis = {
            "task_type": "unknown",
            "task_tags": [],
            "quality_score": 0.0,
            "quality_notes": f"LLM 返回解析失败: {response[:200]}",
        }

    return RequestScanResult(
        request_id=request_id,
        request_text=request_txt,
        task_type=analysis.get("task_type", "unknown"),
        task_tags=analysis.get("task_tags", []),
        input_files=input_files,
        output_files=output_files,
        quality_score=analysis.get("quality_score", 0.0),
        quality_notes=analysis.get("quality_notes", ""),
        has_code=has_code,
    )


async def scan_all(
    data_dir: Path,
    llm: LLMClient,
    *,
    concurrency: int = 5,
    limit: int | None = None,
    model: str | None = None,
) -> list[RequestScanResult]:
    """遍历 data_dir 下所有 request 目录并发扫描."""
    md = MarkItDown(enable_plugins=False)

    # 收集所有 request 目录（包含 request/ 子目录的才算）
    request_dirs = sorted(
        d for d in data_dir.iterdir()
        if d.is_dir() and (d / "request").exists()
    )

    if limit:
        request_dirs = request_dirs[:limit]

    logger.info("发现 %d 个 request 目录", len(request_dirs))

    sem = asyncio.Semaphore(concurrency)
    results: list[RequestScanResult] = []
    errors: list[dict] = []

    async def _process(rd: Path) -> None:
        async with sem:
            try:
                logger.info("扫描: %s", rd.name)
                result = await scan_request(rd, llm, md, model=model)
                results.append(result)
            except Exception as e:
                logger.error("扫描失败 %s: %s", rd.name, e)
                errors.append({"request_id": rd.name, "error": str(e)})

    await asyncio.gather(*[_process(rd) for rd in request_dirs])

    if errors:
        logger.warning("%d 个 request 扫描失败", len(errors))

    return results


def write_results(results: list[RequestScanResult], output_path: Path) -> None:
    """将结果写入 JSONL 文件."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")
    logger.info("结果已写入: %s (%d 条)", output_path, len(results))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量扫描 request 目录，评估质量和任务类型",
    )
    parser.add_argument("data_dir", nargs="?", type=Path, default=None, help="request 数据根目录 (默认读取 config.yaml 中的 data_dir)")
    parser.add_argument("--output", "-o", type=Path, default=Path("results.jsonl"), help="输出文件路径")
    parser.add_argument("--config", "-c", type=str, default="config.yaml", help="配置文件路径")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")
    parser.add_argument("--limit", type=int, default=None, help="限制扫描数量（调试用）")
    parser.add_argument("--model", type=str, default=None, help="指定 LLM 模型")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    config = load_config(args.config)

    # data_dir: 命令行参数 > config.yaml 中的 data_dir
    data_dir = args.data_dir or Path(config.data_dir)
    if not data_dir.exists():
        logger.error("数据目录不存在: %s", data_dir)
        sys.exit(1)
    args.data_dir = data_dir

    llm = LLMClient(config)

    results = await scan_all(
        args.data_dir,
        llm,
        concurrency=args.concurrency,
        limit=args.limit,
        model=args.model,
    )

    write_results(results, args.output)

    # 简要统计
    if results:
        avg_score = sum(r.quality_score for r in results) / len(results)
        types = {}
        for r in results:
            types[r.task_type] = types.get(r.task_type, 0) + 1
        logger.info("平均质量评分: %.2f", avg_score)
        logger.info("任务类型分布: %s", json.dumps(types, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
