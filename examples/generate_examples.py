"""Generate the illustrative example transcripts in examples/.

Run from the project root:  ``python examples/generate_examples.py``

Each example is a REAL end-to-end run of Loki's loop — prompt building, code
extraction, sandboxed execution, and skill/lesson capture all execute for
real. The only scripted part is the LLM itself: a stand-in "brain" replays
canned replies so the transcript is deterministic. Every code block in the
generated reports was actually executed in the sandbox; only the LLM's words
were canned. Machine-specific paths are redacted to ``$WORKDIR``.

Re-running this script regenerates the example markdown files.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from loki.agent import Agent, AgentConfig  # noqa: E402
from loki.memory import ExperienceMemory  # noqa: E402
from loki.skills import SkillLibrary  # noqa: E402

HEADER = """\
> **Illustrative example.** This is a real end-to-end run of Loki's loop —
> prompt building, code extraction, sandboxed execution, and skill/lesson
> capture all ran for real. The LLM's replies were scripted (a stand-in
> "brain") to keep the example deterministic. Every code block below was
> actually executed in the sandbox. `$WORKDIR` stands in for the
> machine-specific working directory used when this was generated.
"""


class ScriptedLLM:
    """Deterministic stand-in brain: replays canned replies in call order."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)

    def chat(self, messages, temperature=0.2):
        assert self.replies, "scripted brain ran out of replies"
        return self.replies.pop(0)


def run_scenario(tag: str, goal: str, setup_files: dict[str, str], replies_tpl: list[str]) -> str:
    """Run one scenario end-to-end; return its labeled markdown transcript.

    ``{path}`` placeholders in the scripted replies are baked with the real
    data-file path before the run, then redacted to ``$WORKDIR`` afterwards.
    """
    root = Path(tempfile.mkdtemp(prefix=f"loki_example_{tag}_"))
    workdir = root / "work"
    workdir.mkdir(parents=True)
    for filename, content in setup_files.items():
        (workdir / filename).write_text(content, encoding="utf-8")
    data_path = str(workdir / next(iter(setup_files)))
    replies = [reply.replace("{path}", data_path) for reply in replies_tpl]

    said: list[str] = []
    agent = Agent(
        llm=ScriptedLLM(replies),
        workdir=workdir,
        skills=SkillLibrary(root / "skills.json"),
        memory=ExperienceMemory(root / "memory.jsonl"),
        config=AgentConfig(max_iters=5, timeout=10.0),
        narrator=said.append,
    )
    report = agent.run(goal)

    narration = "\n".join(f"- {line}" for line in said)
    markdown = f"{HEADER}\n## What Loki said\n\n{narration}\n\n---\n\n{report.to_markdown()}\n"
    markdown = markdown.replace(str(workdir), "$WORKDIR").replace(str(root), "$ROOT")
    shutil.rmtree(root, ignore_errors=True)
    return markdown


def scenario_word_count() -> tuple[str, str, dict[str, str], list[str]]:
    """Success on the first attempt: word frequencies in a text file."""
    goal = "Read sample.txt and print the 5 most frequent words with their counts."
    setup = {
        "sample.txt": (
            "the quick brown fox jumps over the lazy dog\n"
            "the dog barked at the fox and the fox ran\n"
            "the quick dog chased the brown fox through the woods\n"
        )
    }
    code = (
        "from collections import Counter\n"
        "import re\n"
        "from pathlib import Path\n"
        "\n"
        'text = Path("{path}").read_text(encoding="utf-8").lower()\n'
        'words = re.findall(r"[a-z]+", text)\n'
        "for word, count in Counter(words).most_common(5):\n"
        '    print(f"{word}: {count}")\n'
    )
    replies = [
        "Plan: read the file, lowercase it, tokenize words with a regex, count with\n"
        "collections.Counter, and print the 5 most common.\n\n"
        f"```python\n{code}```\n",
        json.dumps(
            {
                "name": "word_frequency_counter",
                "description": "Count word frequencies in a text file; return the top N pairs.",
                "code": "from collections import Counter\n"
                "import re\n"
                "from pathlib import Path\n"
                "\n"
                "def word_frequency_counter(path, n=5):\n"
                '    """Return the n most common words in the text file at *path*."""\n'
                '    text = Path(path).read_text(encoding="utf-8").lower()\n'
                '    words = re.findall(r"[a-z]+", text)\n'
                "    return Counter(words).most_common(n)\n",
            }
        ),
        json.dumps(
            {
                "what_worked": "Counter.most_common produced the ranking in a single call",
                "what_failed": "nothing — the first attempt ran clean",
                "lesson": "for frequency tasks, reach for collections.Counter "
                "before writing manual loops",
            }
        ),
    ]
    return "example_run_word_count.md", goal, setup, replies


def scenario_csv_average() -> tuple[str, str, dict[str, str], list[str]]:
    """Fail-then-fix: wrong column name on the first attempt, corrected on retry."""
    goal = "Compute the average price from data.csv and print it rounded to 2 decimals."
    setup = {"data.csv": "product,price\nwidget,19.99\ngadget,29.50\ndoohickey,9.99\n"}
    broken = (
        "import csv\n"
        "from pathlib import Path\n"
        "\n"
        'rows = list(csv.DictReader(Path("{path}").open(encoding="utf-8")))\n'
        'avg = sum(float(r["cost"]) for r in rows) / len(rows)\n'
        'print(f"{avg:.2f}")\n'
    )
    fixed = (
        "import csv\n"
        "from pathlib import Path\n"
        "\n"
        'with Path("{path}").open(encoding="utf-8") as f:\n'
        "    rows = list(csv.DictReader(f))\n"
        'print("columns:", list(rows[0].keys()))\n'
        'avg = sum(float(r["price"]) for r in rows) / len(rows)\n'
        'print(f"{avg:.2f}")\n'
    )
    replies = [
        "Plan: read the CSV with csv.DictReader and average the cost column.\n\n"
        f"```python\n{broken}```\n",
        "The bug: the column is called 'price', not 'cost' — the KeyError says so.\n"
        "This time I'll print the headers first so there's no guessing.\n\n"
        f"```python\n{fixed}```\n",
        json.dumps(
            {
                "name": "csv_column_average",
                "description": "Compute the average of a numeric column in a CSV file.",
                "code": "import csv\n"
                "from pathlib import Path\n"
                "\n"
                "def csv_column_average(path, column):\n"
                '    """Return the average of *column* in the CSV file at *path*."""\n'
                '    with Path(path).open(encoding="utf-8") as f:\n'
                "        rows = list(csv.DictReader(f))\n"
                "    values = [float(r[column]) for r in rows]\n"
                "    return sum(values) / len(values)\n",
            }
        ),
        json.dumps(
            {
                "what_worked": "printing the headers first revealed the real column name",
                "what_failed": "assumed the column was named 'cost' without checking",
                "lesson": "always inspect CSV headers before assuming column names",
            }
        ),
    ]
    return "example_run_csv_average.md", goal, setup, replies


def main() -> None:
    out_dir = ROOT / "examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    for scenario in (scenario_word_count, scenario_csv_average):
        filename, goal, setup, replies = scenario()
        tag = filename.replace("example_run_", "").replace(".md", "")
        markdown = run_scenario(tag, goal, setup, replies)
        (out_dir / filename).write_text(markdown, encoding="utf-8")
        print(f"wrote examples/{filename}")


if __name__ == "__main__":
    main()
