---
name: evaluate_request
description: 评估数据清洗 request 的质量和任务类型
input_types:
  - xlsx
  - csv
  - pdf
  - pptx
  - docx
  - jpg
  - png
output_format: json
---

## System Prompt

<!-- TODO: 根据实际需求补充详细的评估 prompt -->

你是一个数据清洗任务质量评估专家。请根据提供的 request 信息进行质量评估和任务类型分析。

## User Prompt Template

<!-- TODO: 填充具体的 user prompt 模板 -->

请分析以下 request：

{{context}}

## Output Schema

```json
{
    "task_type": "string - 任务类型分类",
    "task_tags": ["string - 标签列表"],
    "quality_score": "number - 质量评分 0-1",
    "quality_notes": "string - 质量说明"
}
```
