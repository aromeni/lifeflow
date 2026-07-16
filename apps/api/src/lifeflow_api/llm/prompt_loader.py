"""Versioned prompt files (skill §6.3: prompts are files, never inline).

A prompt lives at prompts/<task>.md — e.g. prompts/signal_extraction_v1.md —
with a `## System` section and a `## User Template` section. The user template
is rendered with named placeholders from input_data. New behaviour means a new
version file; released prompts are never edited in place.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# apps/api/src/lifeflow_api/llm/prompt_loader.py → repository root is 5 up.
_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PROMPTS_DIR = _REPO_ROOT / "prompts"


class PromptNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Prompt:
    task: str
    system: str
    user_template: str

    def render_user(self, input_data: dict[str, Any]) -> str:
        return self.user_template.format(**input_data)


@lru_cache(maxsize=32)
def _read_prompt(path: Path, task: str) -> Prompt:
    if not path.exists():
        raise PromptNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    system, user_template = "", ""
    section = None
    lines: dict[str, list[str]] = {"system": [], "user": []}
    for line in text.splitlines():
        if line.strip().lower() == "## system":
            section = "system"
            continue
        if line.strip().lower() == "## user template":
            section = "user"
            continue
        if section:
            lines[section].append(line)
    system = "\n".join(lines["system"]).strip()
    user_template = "\n".join(lines["user"]).strip()
    if not system or not user_template:
        raise PromptNotFoundError(f"Prompt {task} must contain System and User Template sections.")
    return Prompt(task=task, system=system, user_template=user_template)


def load_prompt(task: str, *, prompts_dir: str | None = None) -> Prompt:
    base = Path(prompts_dir) if prompts_dir else DEFAULT_PROMPTS_DIR
    return _read_prompt(base / f"{task}.md", task)
