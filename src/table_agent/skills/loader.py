"""Skill 加载器 - 扫描并解析 SKILL.md"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from ..models import SkillConfig, SkillMeta


class SkillLoader:
    """加载 Anthropic 风格的 Skill 定义

    目录结构:
        skills/
        ├── extract_table/
        │   └── SKILL.md
        └── classify_data/
            └── SKILL.md
    """

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._meta_cache: dict[str, SkillMeta] = {}
        self._full_cache: dict[str, SkillConfig] = {}

    def load_metadata(self) -> list[SkillMeta]:
        """第一阶段：只加载 name + description (渐进式披露)

        只读取 YAML frontmatter，不加载完整内容，节省 token。
        """
        if self._meta_cache:
            return list(self._meta_cache.values())

        metas: list[SkillMeta] = []
        if not self.skills_dir.exists():
            return metas

        for skill_dir in sorted(self.skills_dir.iterdir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            fm, _ = self._parse_skill_md(skill_md)
            name = fm.get("name", skill_dir.name)
            description = fm.get("description", "")

            meta = SkillMeta(
                name=name,
                description=description,
                skill_dir=skill_dir,
            )
            metas.append(meta)
            self._meta_cache[name] = meta

        return metas

    def load_full(self, skill_name: str) -> SkillConfig:
        """第二阶段：加载选中 skill 的完整 SKILL.md 内容"""
        if skill_name in self._full_cache:
            return self._full_cache[skill_name]

        # 确保元数据已加载
        if not self._meta_cache:
            self.load_metadata()

        meta = self._meta_cache.get(skill_name)
        if meta is None:
            raise ValueError(f"Skill 不存在: {skill_name}")

        skill_md = meta.skill_dir / "SKILL.md"
        fm, content = self._parse_skill_md(skill_md)

        config = SkillConfig(
            name=meta.name,
            description=meta.description,
            skill_dir=meta.skill_dir,
            full_content=content,
            input_types=fm.get("input_types", []),
            output_format=fm.get("output_format", "json"),
        )
        self._full_cache[skill_name] = config
        return config

    @staticmethod
    def _parse_skill_md(path: Path) -> tuple[dict, str]:
        """解析 SKILL.md 的 YAML frontmatter 和 markdown 内容"""
        post = frontmatter.load(str(path))
        return dict(post.metadata), post.content

    def list_skills(self) -> list[str]:
        """返回所有可用 skill 名称"""
        if not self._meta_cache:
            self.load_metadata()
        return list(self._meta_cache.keys())
