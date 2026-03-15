"""评估报告生成"""

from __future__ import annotations

import base64
import html
import json
import logging
from pathlib import Path

from .models import BenchmarkResult, TestCaseResult

logger = logging.getLogger(__name__)


class BenchmarkReporter:
    """生成评估报告"""

    @staticmethod
    def print_summary(result: BenchmarkResult) -> None:
        """打印评估摘要到控制台"""
        print(f"\n{'='*50}")
        print("SpreadsheetBench 评估结果")
        print(f"{'='*50}")
        print(f"模型: {result.model_used}")
        print(f"时间: {result.timestamp}")
        print(f"\n总测试用例: {result.total_cases}")
        print(f"已完成: {result.completed}")
        print(f"失败: {result.failed}")
        print(f"\n整体准确率: {result.overall_accuracy:.2%}")
        print(f"Cell-Level 准确率: {result.cell_level_accuracy:.2%}")
        print(f"Sheet-Level 准确率: {result.sheet_level_accuracy:.2%}")

        if result.errors:
            print(f"\n失败用例 ({len(result.errors)}):")
            for err in result.errors[:10]:
                print(f"  - {err['entry_id']}#{err.get('test_num', '?')}: {err['error'][:100]}")

        print(f"{'='*50}\n")

    @staticmethod
    def save_results(result: BenchmarkResult, output_dir: str) -> None:
        """保存详细结果"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 汇总 JSON
        summary = {
            "total_cases": result.total_cases,
            "completed": result.completed,
            "failed": result.failed,
            "overall_accuracy": result.overall_accuracy,
            "cell_level_accuracy": result.cell_level_accuracy,
            "sheet_level_accuracy": result.sheet_level_accuracy,
            "model_used": result.model_used,
            "timestamp": result.timestamp,
            "errors": result.errors,
        }
        summary_path = out / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        logger.info("汇总结果已保存: %s", summary_path)

        # 详细 JSONL（含完整执行轨迹）
        details_path = out / "details.jsonl"
        with open(details_path, "w", encoding="utf-8") as f:
            for tcr in result.per_task_results:
                # 构建每轮步骤的简化记录
                steps_data = []
                for step in tcr.react_result.steps:
                    step_dict = {
                        "round": step.round,
                        "thought": step.thought,
                        "action": step.action,
                        "code": step.code,
                        "screenshot_paths": step.screenshot_paths,
                        "spreadsheet_path": step.spreadsheet_path,
                    }
                    if step.execution_result:
                        step_dict["execution"] = {
                            "success": step.execution_result.success,
                            "stdout": step.execution_result.stdout[:2000],
                            "stderr": step.execution_result.stderr[:2000],
                            "timed_out": step.execution_result.timed_out,
                        }
                    steps_data.append(step_dict)

                line = {
                    "entry_id": tcr.entry_id,
                    "test_num": tcr.test_num,
                    "instruction_type": tcr.instruction_type,
                    "accuracy": tcr.comparison.accuracy,
                    "total_cells": tcr.comparison.total_cells,
                    "matched_cells": tcr.comparison.matched_cells,
                    "rounds": tcr.react_result.total_rounds,
                    "success": tcr.react_result.success,
                    "elapsed_seconds": tcr.elapsed_seconds,
                    "error": tcr.comparison.error,
                    "mismatches": tcr.comparison.mismatches[:10],
                    "steps": steps_data,
                }
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        logger.info("详细结果已保存: %s (%d 条)", details_path, len(result.per_task_results))

        # 生成 HTML 报告
        BenchmarkReporter.generate_html_report(result, output_dir)

    @staticmethod
    def generate_html_report(result: BenchmarkResult, output_dir: str) -> None:
        """生成自包含 HTML 可视化报告"""
        out = Path(output_dir)
        report_path = out / "report.html"

        task_cards = []
        for tcr in result.per_task_results:
            task_cards.append(_render_task_card(tcr))

        html_content = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpreadsheetBench 评估报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; color: #333; line-height: 1.6; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ text-align: center; margin: 20px 0; color: #1a1a1a; }}

/* 仪表盘 */
.dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 30px; }}
.metric {{ background: #fff; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.metric .value {{ font-size: 2em; font-weight: 700; color: #2563eb; }}
.metric .label {{ font-size: 0.9em; color: #666; margin-top: 4px; }}
.metric.accent .value {{ color: #059669; }}
.metric.warn .value {{ color: #d97706; }}

/* 任务卡片 */
.task-card {{ background: #fff; border-radius: 12px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden; }}
.task-header {{ padding: 16px 20px; cursor: pointer; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid #eee; }}
.task-header:hover {{ background: #fafafa; }}
.task-header .badge {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }}
.badge-success {{ background: #d1fae5; color: #065f46; }}
.badge-fail {{ background: #fee2e2; color: #991b1b; }}
.badge-type {{ background: #e0e7ff; color: #3730a3; }}
.task-header .accuracy {{ font-size: 1.4em; font-weight: 700; margin-left: auto; }}
.task-header .meta {{ font-size: 0.85em; color: #666; }}
.task-body {{ display: none; padding: 20px; }}
.task-body.open {{ display: block; }}

/* 指令 */
.instruction {{ background: #f8fafc; border-left: 4px solid #2563eb; padding: 12px 16px; margin-bottom: 16px; font-size: 0.95em; border-radius: 0 8px 8px 0; }}

/* 时间线 */
.timeline {{ position: relative; padding-left: 30px; }}
.timeline::before {{ content: ''; position: absolute; left: 12px; top: 0; bottom: 0; width: 2px; background: #ddd; }}
.step {{ position: relative; margin-bottom: 20px; }}
.step::before {{ content: ''; position: absolute; left: -22px; top: 6px; width: 12px; height: 12px; border-radius: 50%; background: #2563eb; border: 2px solid #fff; box-shadow: 0 0 0 2px #2563eb; }}
.step.step-fail::before {{ background: #ef4444; box-shadow: 0 0 0 2px #ef4444; }}
.step.step-done::before {{ background: #059669; box-shadow: 0 0 0 2px #059669; }}
.step-label {{ font-weight: 600; font-size: 0.9em; color: #666; margin-bottom: 6px; }}

/* 思考 */
.thought {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 12px; margin-bottom: 8px; font-size: 0.9em; white-space: pre-wrap; }}

/* 代码 */
.code-block {{ background: #1e1e1e; color: #d4d4d4; border-radius: 8px; padding: 14px; margin-bottom: 8px; font-family: 'SF Mono', Consolas, monospace; font-size: 0.85em; overflow-x: auto; white-space: pre; }}

/* 执行结果 */
.exec-result {{ border-radius: 8px; padding: 12px; margin-bottom: 8px; font-family: monospace; font-size: 0.85em; white-space: pre-wrap; word-break: break-all; }}
.exec-success {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
.exec-fail {{ background: #fef2f2; border: 1px solid #fecaca; }}

/* 截图 */
.screenshots {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }}
.screenshots img {{ max-width: 400px; max-height: 300px; border: 1px solid #ddd; border-radius: 8px; cursor: pointer; }}
.screenshots img:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}

/* Mismatches */
.mismatches {{ margin-top: 12px; }}
.mismatches table {{ width: 100%; border-collapse: collapse; font-size: 0.85em; }}
.mismatches th {{ background: #f1f5f9; padding: 8px; text-align: left; border-bottom: 2px solid #e2e8f0; }}
.mismatches td {{ padding: 8px; border-bottom: 1px solid #e2e8f0; }}
.mismatches .expected {{ color: #059669; }}
.mismatches .actual {{ color: #ef4444; }}

.toggle {{ cursor: pointer; color: #2563eb; font-size: 0.85em; }}
.toggle:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
<h1>SpreadsheetBench 评估报告</h1>
<p style="text-align:center;color:#666;margin-bottom:20px;">模型: {html.escape(result.model_used)} | {html.escape(result.timestamp)}</p>

<div class="dashboard">
  <div class="metric accent"><div class="value">{result.overall_accuracy:.1%}</div><div class="label">整体准确率</div></div>
  <div class="metric"><div class="value">{result.cell_level_accuracy:.1%}</div><div class="label">Cell-Level</div></div>
  <div class="metric"><div class="value">{result.sheet_level_accuracy:.1%}</div><div class="label">Sheet-Level</div></div>
  <div class="metric"><div class="value">{result.completed}</div><div class="label">已完成</div></div>
  <div class="metric warn"><div class="value">{result.failed}</div><div class="label">失败</div></div>
  <div class="metric"><div class="value">{result.total_cases}</div><div class="label">总用例</div></div>
</div>

{''.join(task_cards)}

</div>
<script>
document.querySelectorAll('.task-header').forEach(h => {{
  h.addEventListener('click', () => {{
    h.nextElementSibling.classList.toggle('open');
  }});
}});
</script>
</body>
</html>"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("HTML 报告已生成: %s", report_path)


def _render_task_card(tcr: TestCaseResult) -> str:
    """渲染单个测试用例卡片"""
    acc = tcr.comparison.accuracy
    acc_color = "#059669" if acc >= 0.8 else "#d97706" if acc >= 0.5 else "#ef4444"
    success_badge = '<span class="badge badge-success">通过</span>' if tcr.react_result.success else '<span class="badge badge-fail">失败</span>'
    type_badge = f'<span class="badge badge-type">{html.escape(tcr.instruction_type)}</span>'

    # 渲染步骤时间线
    steps_html = []
    for step in tcr.react_result.steps:
        step_class = "step"
        if step.action == "done":
            step_class += " step-done"
        elif step.execution_result and not step.execution_result.success:
            step_class += " step-fail"

        parts = [f'<div class="{step_class}">']
        parts.append(f'<div class="step-label">第 {step.round} 轮 — {html.escape(step.action)}</div>')

        # 截图
        if step.screenshot_paths:
            parts.append('<div class="screenshots">')
            for sp in step.screenshot_paths:
                p = Path(sp)
                if p.exists():
                    b64 = base64.b64encode(p.read_bytes()).decode()
                    parts.append(f'<img src="data:image/png;base64,{b64}" alt="round {step.round}">')
            parts.append('</div>')

        # 思考
        if step.thought:
            parts.append(f'<div class="thought">{html.escape(step.thought)}</div>')

        # 代码
        if step.code:
            parts.append(f'<div class="code-block">{html.escape(step.code)}</div>')

        # 执行结果
        if step.execution_result:
            er = step.execution_result
            cls = "exec-success" if er.success else "exec-fail"
            exec_text = ""
            if er.stdout:
                exec_text += er.stdout[:1000]
            if er.stderr:
                exec_text += ("\n" if exec_text else "") + er.stderr[:1000]
            if er.timed_out:
                exec_text += "\n⏰ 执行超时"
            if exec_text:
                parts.append(f'<div class="exec-result {cls}">{html.escape(exec_text)}</div>')

        parts.append('</div>')
        steps_html.append('\n'.join(parts))

    # Mismatches 表格
    mismatch_html = ""
    if tcr.comparison.mismatches:
        rows = []
        for mm in tcr.comparison.mismatches[:20]:
            rows.append(f'<tr><td>{html.escape(str(mm.get("cell", "")))}</td>'
                       f'<td>{html.escape(str(mm.get("sheet", "")))}</td>'
                       f'<td class="expected">{html.escape(str(mm.get("expected", "")))}</td>'
                       f'<td class="actual">{html.escape(str(mm.get("actual", "")))}</td></tr>')
        mismatch_html = f"""
<div class="mismatches">
<table>
<tr><th>单元格</th><th>Sheet</th><th>期望值</th><th>实际值</th></tr>
{''.join(rows)}
</table>
</div>"""

    return f"""
<div class="task-card">
  <div class="task-header">
    {success_badge} {type_badge}
    <span><strong>{html.escape(tcr.entry_id)}#{tcr.test_num}</strong></span>
    <span class="meta">{tcr.react_result.total_rounds} 轮 | {tcr.elapsed_seconds:.1f}s</span>
    <span class="accuracy" style="color:{acc_color}">{acc:.0%}</span>
  </div>
  <div class="task-body">
    <div class="instruction">{html.escape(tcr.react_result.instruction[:500])}</div>
    <div class="timeline">
      {''.join(steps_html)}
    </div>
    {mismatch_html}
  </div>
</div>"""
