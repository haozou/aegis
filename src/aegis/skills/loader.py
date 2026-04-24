"""Skills loader with hot-reload support."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..utils.logging import get_logger
from .types import Skill, SkillMetadata, SkillTrigger

logger = get_logger(__name__)


def _parse_skill_md(path: Path) -> Skill | None:
    """Parse a SKILL.md file into a Skill object."""
    try:
        import frontmatter
        post = frontmatter.load(str(path))
        meta_dict = dict(post.metadata)

        # Handle keywords - can be string or list
        keywords = meta_dict.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",")]

        # Handle tools
        tools = meta_dict.get("tools", [])
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",")]

        metadata = SkillMetadata(
            name=meta_dict.get("name", path.parent.name),
            description=meta_dict.get("description", ""),
            version=str(meta_dict.get("version", "1.0.0")),
            trigger=SkillTrigger(meta_dict.get("trigger", "keyword")),
            keywords=keywords,
            tools=tools,
            priority=int(meta_dict.get("priority", 0)),
            enabled=bool(meta_dict.get("enabled", True)),
        )
        return Skill(
            metadata=metadata,
            system_prompt=post.content.strip(),
            source_path=str(path),
        )
    except ImportError:
        # Fallback: parse YAML frontmatter manually
        try:
            import yaml
            content = path.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    meta_dict = yaml.safe_load(parts[1]) or {}
                    body = parts[2].strip()
                    keywords = meta_dict.get("keywords", [])
                    if isinstance(keywords, str):
                        keywords = [k.strip() for k in keywords.split(",")]
                    tools = meta_dict.get("tools", [])
                    if isinstance(tools, str):
                        tools = [t.strip() for t in tools.split(",")]
                    metadata = SkillMetadata(
                        name=meta_dict.get("name", path.parent.name),
                        description=meta_dict.get("description", ""),
                        keywords=keywords,
                        tools=tools,
                    )
                    return Skill(metadata=metadata, system_prompt=body, source_path=str(path))
        except Exception as e:
            logger.error("Failed to parse skill", path=str(path), error=str(e))
        return None
    except Exception as e:
        logger.error("Failed to parse skill", path=str(path), error=str(e))
        return None


class SkillsLoader:
    """Loads and manages skills from SKILL.md files."""

    def __init__(
        self,
        skills_dirs: list[Path],
        hot_reload: bool = True,
    ) -> None:
        self._skills_dirs = skills_dirs
        self._hot_reload = hot_reload
        self._skills: dict[str, Skill] = {}
        self._watcher_task: asyncio.Task[None] | None = None

    async def load_all(self) -> None:
        """Scan all skill directories and load SKILL.md files."""
        self._skills.clear()
        for skills_dir in self._skills_dirs:
            if not skills_dir.exists():
                continue
            for skill_file in skills_dir.rglob("SKILL.md"):
                skill = _parse_skill_md(skill_file)
                if skill and skill.metadata.enabled:
                    self._skills[skill.metadata.name] = skill
                    logger.debug("Loaded skill", name=skill.metadata.name)
        logger.info("Skills loaded", count=len(self._skills))

    async def start_hot_reload(self) -> None:
        """Start watching for skill file changes."""
        if not self._hot_reload:
            return
        try:
            from watchfiles import awatch
            self._watcher_task = asyncio.create_task(self._watch_loop(awatch))
            logger.info("Skills hot-reload started")
        except ImportError:
            logger.warning("watchfiles not installed, hot-reload disabled")

    async def _watch_loop(self, awatch: Any) -> None:
        """Watch for file changes and reload affected skills."""
        watch_paths = [str(d) for d in self._skills_dirs if d.exists()]
        if not watch_paths:
            return
        try:
            async for changes in awatch(*watch_paths):
                for change_type, path in changes:
                    if path.endswith("SKILL.md"):
                        logger.info("Reloading changed skill", path=path)
                        await self.load_all()
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Skills watcher error", error=str(e))

    async def stop(self) -> None:
        """Stop the hot-reload watcher."""
        if self._watcher_task:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
            except asyncio.CancelledError:
                pass

    def get_all(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def set_enabled(self, name: str, enabled: bool) -> bool:
        if name in self._skills:
            self._skills[name].metadata.enabled = enabled
            return True
        return False

    def get_system_prompts_for_message(self, message: str) -> list[str]:
        """Get system prompts from skills that trigger on this message."""
        prompts = []
        message_lower = message.lower()

        for skill in sorted(self._skills.values(), key=lambda s: -s.metadata.priority):
            if not skill.metadata.enabled:
                continue
            trigger = skill.metadata.trigger
            if trigger == SkillTrigger.ALWAYS:
                prompts.append(skill.system_prompt)
            elif trigger == SkillTrigger.KEYWORD:
                if any(kw.lower() in message_lower for kw in skill.metadata.keywords):
                    prompts.append(skill.system_prompt)

        return prompts
