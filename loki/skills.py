"""Persistent skill library: reusable code snippets Loki accumulates over time.

This is the heart of the "self-improving" idea (inspired by the Voyager
research paper's skill library): every successful run gets distilled into a
reusable skill, and future runs retrieve relevant skills to build on past
work instead of starting from zero.

Retrieval is plain keyword-overlap scoring over skill names and
descriptions — deliberately dependency-free (no embeddings). Simple,
inspectable, and honest about what it is.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# Hand-written starter skills so a fresh library isn't empty.
SEED_SKILLS: list[dict[str, str]] = [
    {
        "name": "read_csv_preview",
        "description": "Read a CSV file and return its column names plus the first few rows.",
        "code": (
            "import csv\n"
            "\n"
            "def read_csv_preview(path, n=5):\n"
            '    """Return (columns, first n rows) of a CSV file."""\n'
            '    with open(path, newline="", encoding="utf-8") as f:\n'
            "        reader = csv.DictReader(f)\n"
            "        rows = [row for _, row in zip(range(n), reader)]\n"
            "        columns = reader.fieldnames or []\n"
            "    return columns, rows\n"
        ),
    },
    {
        "name": "fetch_json",
        "description": "HTTP GET a URL and return the parsed JSON body, raising on errors.",
        "code": (
            "import httpx\n"
            "\n"
            "def fetch_json(url, timeout=15.0):\n"
            '    """GET *url* and return parsed JSON; raises on HTTP errors."""\n'
            "    response = httpx.get(url, timeout=timeout)\n"
            "    response.raise_for_status()\n"
            "    return response.json()\n"
        ),
    },
    {
        "name": "extract_emails",
        "description": "Find all unique email addresses in a block of text.",
        "code": (
            "import re\n"
            "\n"
            '_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+")\n'
            "\n"
            "def extract_emails(text):\n"
            '    """Return a sorted list of unique email addresses in *text*."""\n'
            "    return sorted(set(_EMAIL_RE.findall(text)))\n"
        ),
    },
]


@dataclass
class Skill:
    """One reusable capability: a name, a description, and the code."""

    name: str
    description: str
    code: str
    created_at: str = field(default_factory=_utcnow)
    uses: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            code=str(data.get("code", "")),
            created_at=str(data.get("created_at", _utcnow())),
            uses=int(data.get("uses", 0)),
        )


class SkillLibrary:
    """JSON-file-backed store of skills with keyword retrieval."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.skills: dict[str, Skill] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for item in data:
            skill = Skill.from_dict(item)
            self.skills[skill.name] = skill

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [skill.to_dict() for skill in self.skills.values()]
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def ensure_seed(self) -> int:
        """Add the starter skills if the library doesn't have them. Returns count added."""
        added = 0
        for seed in SEED_SKILLS:
            if seed["name"] not in self.skills:
                self.skills[seed["name"]] = Skill.from_dict(seed)
                added += 1
        if added:
            self._persist()
        return added

    def save_skill(self, name: str, description: str, code: str) -> Skill:
        """Save (or update) a skill. Names are lowercase snake_case identifiers."""
        name = name.strip().lower()
        if not _NAME_RE.match(name):
            raise ValueError(
                f"invalid skill name {name!r}: use lowercase letters, digits, underscores"
            )
        if not code.strip():
            raise ValueError("skill code must not be empty")
        skill = Skill(name=name, description=description.strip(), code=code)
        # Preserve history when updating an existing skill.
        if name in self.skills:
            old = self.skills[name]
            skill.created_at = old.created_at
            skill.uses = old.uses
        self.skills[name] = skill
        self._persist()
        return skill

    def find_skills(self, query: str, top_k: int = 5) -> list[Skill]:
        """Return up to *top_k* skills ranked by keyword overlap with *query*."""
        qtokens = _tokens(query)
        if not qtokens:
            return []
        scored: list[tuple[float, int, Skill]] = []
        for skill in self.skills.values():
            stokens = _tokens(f"{skill.name} {skill.description}")
            overlap = len(qtokens & stokens)
            if overlap:
                scored.append((overlap / len(qtokens), skill.uses, skill))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [skill for _, _, skill in scored[:top_k]]

    def record_use(self, name: str) -> None:
        """Bump the use counter for a skill that just helped solve a task."""
        if name in self.skills:
            self.skills[name].uses += 1
            self._persist()
