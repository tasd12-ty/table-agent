# Table Agent

多格式文件语义处理框架 — 支持 PDF / Excel / Word / PPT / CSV / MP4 等文件的自动解析、意图分类和智能处理。

## 架构

```
输入文件 → 文件解析 (MarkItDown/OpenCV) → Skill 路由 (LLM tool calling) → Skill 执行 → 结构化输出
```

核心组件：

| 模块 | 说明 |
|------|------|
| `agent.py` | 主编排器，串联整个 pipeline |
| `llm.py` | LLM 客户端，兼容 OpenAI API 的任意后端 (vLLM / OpenRouter 等) |
| `skills/router.py` | 渐进式 Skill 路由，通过 LLM function calling 自动选择 skill |
| `skills/loader.py` | Skill 发现与加载 (YAML frontmatter + Markdown) |
| `skills/executor.py` | Skill 执行引擎 |
| `parsers/` | 文档解析器 (MarkItDown) 和视频解析器 (OpenCV) |
| `batch.py` | 批量处理，支持并发和重试 |

## 安装

```bash
# 依赖 Python >= 3.11
uv sync
```

## 配置

### config.yaml

所有配置集中在 `config.yaml`，支持 `${ENV_VAR}` 环境变量引用：

```yaml
llm:
  api_key: ${LLM_API_KEY}
  base_url: http://localhost:8000/v1   # vLLM 本地部署
  default_model: Qwen/Qwen3-8B        # 主模型 (任务执行、质量评估)
  router_model: Qwen/Qwen3-8B         # 路由模型 (意图分类, 需支持 tool calling)

video:
  max_frames: 10
  frame_interval_sec: 2

skills_dir: skills/
output_dir: output/
data_dir: data/                        # request 数据目录
```

### 使用本地模型 (vLLM)

1. **启动 vLLM 服务**（需启用 tool calling 支持）：

   ```bash
   vllm serve Qwen/Qwen3-8B \
     --enable-auto-tool-choice \
     --tool-call-parser hermes
   ```

2. **设置环境变量**（vLLM 不校验 key，任意非空值即可）：

   ```bash
   export LLM_API_KEY=token-abc123
   ```

3. **确认模型名称**一致 — `config.yaml` 中的 `default_model` 必须与 vLLM 加载的模型名一致：

   ```bash
   # 查看 vLLM 已加载的模型
   curl http://localhost:8000/v1/models
   ```

### 使用云端服务 (OpenRouter)

修改 `config.yaml`：

```yaml
llm:
  api_key: ${LLM_API_KEY}
  base_url: https://openrouter.ai/api/v1
  default_model: google/gemini-2.0-flash-001
  router_model: google/gemini-2.0-flash-001
```

设置真实 API Key：

```bash
export LLM_API_KEY=sk-or-xxx
```

## 使用

### CLI 命令

```bash
# 单文件处理 (自动路由 skill)
uv run table-agent run document.pdf

# 指定 skill
uv run table-agent run data.xlsx --skill extract_table

# 指定模型
uv run table-agent run report.pdf --model Qwen/Qwen3-8B

# 批量处理
uv run table-agent batch batch_tasks/example_batch.yaml

# 列出可用 skills
uv run table-agent skills
```

### 批量扫描与意图分类

`scripts/scan_requests.py` 用于批量扫描 request 目录，进行质量评估和任务类型分析。

**数据目录结构**（放在 `data/` 下）：

```
data/
├── {request_id}/                        # 请求ID目录
│   ├── request/                         # 必有：请求描述
│   │   └── {request_id}_request.txt     # 请求文本
│   ├── input/                           # 可选：输入文件
│   │   ├── *.xlsx / *.csv / *.pdf       # 各种格式
│   │   ├── *.jpg / *.png               # 图片
│   │   └── *.docx / *.pptx            # Office 文档
│   ├── output/                          # 必有：输出结果
│   │   ├── output_*.xlsx               # Excel 结果文件
│   │   ├── visualization.txt           # 可视化描述 (含多轮聊天内容)
│   │   └── output-text-re.txt          # 文本输出 (可选)
│   └── code/                            # 可选：执行代码
│       └── {request_id}.py             # Python 脚本
```

**运行扫描**：

```bash
# 默认扫描 config.yaml 中配置的 data_dir
uv run python scripts/scan_requests.py

# 指定数据目录
uv run python scripts/scan_requests.py /path/to/data

# 常用选项
uv run python scripts/scan_requests.py \
  --limit 10 \                # 限制扫描数量 (调试用)
  --concurrency 5 \           # 并发数
  --model Qwen/Qwen3-8B \    # 指定模型
  --output results.jsonl \    # 输出文件
  -v                          # 详细日志
```

**输出格式** (JSONL)：

```json
{
  "request_id": "uuid-xxx",
  "request_text": "原始需求...",
  "task_type": "数据清洗",
  "task_tags": ["Excel", "去重"],
  "input_files": ["data.xlsx"],
  "output_files": ["output_1.xlsx", "visualization.txt"],
  "quality_score": 0.85,
  "quality_notes": "基本完成，输出格式正确",
  "has_code": true
}
```

### Python API

```python
import asyncio
from table_agent.agent import TableAgent

async def main():
    agent = TableAgent(config_path="config.yaml")

    # 自动路由
    result = await agent.process("document.pdf")
    print(result.model_dump_json(indent=2))

    # 指定 skill
    result = await agent.process("data.xlsx", skill_name="extract_table")

asyncio.run(main())
```

## Skills

框架通过 `skills/` 目录下的 SKILL.md 文件定义处理技能。SkillLoader 自动发现并加载。

### 自定义 Skills

| Skill | 说明 |
|-------|------|
| `classify_data` | 对文档内容进行语义分类和打标签 |
| `extract_table` | 从文档中提取结构化表格数据 |
| `evaluate_request` | 评估数据清洗请求的质量 |

### Anthropic 官方 Skills

| Skill | 说明 |
|-------|------|
| `xlsx` | Excel/CSV 处理，含 recalc 脚本和 Office 工具 |
| `pdf` | PDF 处理，含表单填充、文本提取脚本 |
| `pptx` | PowerPoint 处理，含模板编辑和创建 |
| `docx` | Word 文档处理，含 XML 编辑工具 |
| `skill-creator` | 创建和评估 skills 的元工具 |
| `doc-coauthoring` | 文档协作工作流 |
| `claude-api` | Claude API 多语言参考文档 |
| `mcp-builder` | MCP 服务器构建 |
| `frontend-design` | 前端界面设计 |
| `canvas-design` | Canvas 设计 |
| `webapp-testing` | Web 应用测试 (Playwright) |
| `web-artifacts-builder` | Web artifacts 构建 |
| `algorithmic-art` | 算法艺术生成 |
| `brand-guidelines` | 品牌指南 |
| `internal-comms` | 内部沟通模板 |
| `slack-gif-creator` | Slack GIF 创建 |
| `theme-factory` | 主题工厂 |

### SKILL.md 格式

```markdown
---
name: my_skill
description: "技能描述"
input_types: [pdf, xlsx, csv]
output_format: json
---

# Skill Name

## System Prompt
系统提示词...

## User Prompt Template
用户提示词模板，支持占位符：{text_content}, {file_type}, {source_path}, {metadata}

## Output Schema
输出 JSON Schema...
```

## 项目结构

```
table-agent/
├── config.yaml                  # 主配置文件
├── .env.example                 # 环境变量模板
├── pyproject.toml               # 项目依赖
├── main.py                      # CLI 备用入口
├── src/table_agent/
│   ├── agent.py                 # 主编排器
│   ├── llm.py                   # LLM 客户端
│   ├── config.py                # 配置加载
│   ├── models.py                # 数据模型 (Pydantic)
│   ├── batch.py                 # 批量处理
│   ├── parsers/
│   │   ├── document.py          # 文档解析 (MarkItDown)
│   │   └── video.py             # 视频解析 (OpenCV)
│   └── skills/
│       ├── loader.py            # Skill 发现与加载
│       ├── router.py            # Skill 路由 (LLM tool calling)
│       └── executor.py          # Skill 执行
├── skills/                      # Skill 定义目录
├── scripts/
│   └── scan_requests.py         # 批量扫描评估脚本
├── batch_tasks/                 # 批量任务配置
├── data/                        # Request 数据目录
├── output/                      # 处理结果输出
└── examples/
    └── example_usage.py         # Python API 使用示例
```
