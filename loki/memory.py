"""Experience memory: an append-only log of what Loki tried and learned.

After every run — success or failure — Loki writes down what worked, what
didn't, and the lesson. Future runs retrieve the most relevant lessons by
keyword overlap and get them injected into their prompt, so the same
mistake (hopefully) only gets made once.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


SEED_EXPERIENCES: list[dict[str, str]] = [
    {
        "task": "first run (built-in)",
        "what_worked": "starting with a tiny, runnable first attempt",
        "what_failed": "nothing yet — the timeline is fresh",
        "lesson": "Prefer small, testable first attempts and print intermediate results "
        "so failures are diagnosable from the output alone.",
    },
]


@dataclass
class Experience:
    """One logged run: what was tried, what worked, what failed, the lesson."""

    task: str
    what_worked: str
    what_failed: str
    lesson: str
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Experience:
        return cls(
            task=str(data.get("task", "")),
            what_worked=str(data.get("what_worked", "")),
            what_failed=str(data.get("what_failed", "")),
            lesson=str(data.get("lesson", "")),
            created_at=str(data.get("created_at", _utcnow())),
        )


class ExperienceMemory:
    """Append-only JSONL store of experiences with keyword retrieval."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.entries: list[Experience] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                self.entries.append(Experience.from_dict(json.loads(line)))

    def ensure_seed(self) -> int:
        """Add starter experience(s) to an empty memory. Returns count added."""
        if self.entries:
            return 0
        added = 0
        for seed in SEED_EXPERIENCES:
            self.log(
                task=seed["task"],
                what_worked=seed["what_worked"],
                what_failed=seed["what_failed"],
                lesson=seed["lesson"],
            )
            added += 1
        return added

    def log(self, task: str, what_worked: str, what_failed: str, lesson: str) -> Experience:
        """Append one experience to the log and return it."""
        entry = Experience(
            task=task.strip(),
            what_worked=what_worked.strip(),
            what_failed=what_failed.strip(),
            lesson=lesson.strip(),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
        self.entries.append(entry)
        return entry

    def retrieve(self, query: str, top_k: int = 3) -> list[Experience]:
        """Return up to *top_k* experiences ranked by keyword overlap with *query*."""
        qtokens = _tokens(query)
        if not qtokens:
            return []
        scored: list[tuple[float, Experience]] = []
        for entry in self.entries:
            etokens = _tokens(f"{entry.task} {entry.lesson}")
            overlap = len(qtokens & etokens)
            if overlap:
                scored.append((overlap / len(qtokens), entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]
