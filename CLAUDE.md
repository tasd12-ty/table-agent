# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

## 构建与运行

```bash
uv sync                                          # 安装依赖
uv run table-agent run <file>                     # 处理单个文件（自动路由技能）
uv run table-agent run <file> --skill extract_table  # 指定技能
uv run table-agent batch batch_tasks/<config>.yaml   # 批量处理
uv run table-agent skills                         # 列出可用技能
uv run python scripts/scan_requests.py data/ --limit 5 -v  # 扫描请求
```

目前尚无测试套件。需要 Python >= 3.11。

### 系统依赖

- **LibreOffice**（可选但推荐）：ReAct agent 用于将 xlsx 渲染为截图供 LLM 视觉推理。无 LibreOffice 时自动回退为文本模式。
  ```bash
  # macOS
  brew install --cask libreoffice
  # Linux
  sudo apt install libreoffice
  ```

## 架构

系统是一个异步流水线：**文件 → 解析 → 路由 → 执行 → 结果**。

**流水线流程**（`agent.py` 编排）：
1. `DocumentParser`（MarkItDown）或 `VideoParser`（OpenCV）将输入转换为 `ParsedContent`
2. `SkillRouter` 使用 LLM 函数调用从轻量级元数据（仅 name + description——"渐进式披露"）中选择最佳技能
3. `SkillExecutor` 从选定的 SKILL.md 中提取 `## System Prompt` 和 `## User Prompt Template` 部分，填充 `{text_content}`、`{file_type}`、`{source_path}`、`{metadata}` 占位符，然后调用 LLM
4. 响应被解析为 JSON（带有代码围栏剥离回退）并生成 `AgentResult`

**LLM 客户端**（`llm.py`）：基于 `openai.AsyncOpenAI` 的轻量封装。后端无关——通过 `config.yaml` 支持 vLLM（本地）或 OpenRouter（云端）。三个方法：`chat`、`chat_with_images`、`chat_with_tools`。

**技能系统**（`skills/`）：
- `loader.py`：两阶段加载——`load_metadata()` 仅读取 YAML 前置元数据用于路由；`load_full()` 读取完整 SKILL.md 内容用于执行
- `router.py`：将技能元数据转换为 OpenAI 工具调用格式，LLM 通过函数调用进行选择
- `executor.py`：用正则表达式提取 `## Section Name` 区块，填充模板
- 技能定义为 `skills/<name>/SKILL.md`，包含 YAML 前置元数据（`name`、`description`，可选 `input_types`、`output_format`）

**配置**（`config.py`）：YAML 格式，支持 `${ENV_VAR}` 插值。关键部分是 `llm`（原名 `openrouter`——旧名称仍兼容）。`LLMConfig` 包含 `api_key`、`base_url`、`default_model`、`router_model`。

**批处理**（`batch.py`）：加载 YAML 任务配置，展开 glob 模式，使用 `asyncio.Semaphore` 控制并发 + 重试，输出 json/jsonl/csv。

## 关键约定

- 所有 LLM 调用均为异步（`async/await`）。CLI 入口点使用 `asyncio.run()` 包装。
- 数据模型使用 Pydantic v2（`BaseModel`）；配置使用 `dataclasses`。
- 全程使用中文提示词和日志消息。
- `scripts/scan_requests.py` 是独立脚本（非包的一部分），通过 `sys.path` 操作从 `src/` 导入。
- `data/` 目录被 gitignore（除 `.gitkeep` 外）。请求数据存放结构：`data/{request_id}/request/`、`input/`、`output/`、`code/`。

## 本地模型配置（vLLM）

默认配置指向 `http://localhost:8000/v1`。启动支持工具调用的 vLLM：

```bash
vllm serve Qwen/Qwen3-8B --enable-auto-tool-choice --tool-call-parser hermes
export LLM_API_KEY=token-abc123
```

`router_model` 必须支持 OpenAI 兼容的函数调用（用于 `SkillRouter`）。`default_model` 用于所有其他 LLM 调用。

## ReAct Agent + SpreadsheetBench 评估

独立于技能系统的多轮推理 agent，用于 SpreadsheetBench 基准测试。

**ReAct 循环**（`src/table_agent/react/`）：
- `agent.py`：观察→思考→行动→执行的多轮循环，支持截图或文本模式
- `renderer.py`：LibreOffice 无头模式将 xlsx 渲染为 PNG 截图
- `executor.py`：subprocess 沙箱执行 LLM 生成的 Python/openpyxl 代码
- `tracer.py`：记录每轮截图、xlsx 快照和完整执行轨迹
- `prompts.py`：中文 system prompt，含 VBA→openpyxl 翻译指南

**评估系统**（`src/table_agent/bench/`）：
- `dataset.py`：加载 SpreadsheetBench 912 条数据
- `comparator.py`：单元格级别对比输出与答案
- `runner.py`：并发评估编排器
- `report.py`：生成 HTML 可视化报告 + JSONL 详细结果

```bash
# 运行评估（需设置 LLM_API_KEY）
uv run python scripts/run_bench.py --limit 10 -v
# 查看 HTML 报告
open output/bench/report.html
```
