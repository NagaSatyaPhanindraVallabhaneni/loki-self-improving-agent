"""Command-line interface: ``python -m loki "your task here"``."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .agent import Agent, AgentConfig, RunReport
from .llm import LLMClient
from .memory import ExperienceMemory
from .skills import SkillLibrary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="loki",
        description="Loki — a self-improving coding agent. Give it a goal; it writes code, "
        "runs it, learns from the result, and files new skills away for next time.",
    )
    parser.add_argument("goal", help="the task to accomplish, e.g. 'count words in notes.txt'")
    parser.add_argument("--max-iters", type=int, default=5, help="max code attempts per run (1-20)")
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="seconds before a run is killed"
    )
    parser.add_argument("--model", default=os.environ.get("LOKI_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--base-url", default=os.environ.get("LOKI_BASE_URL", "https://api.openai.com/v1")
    )
    parser.add_argument("--api-key", default=None, help="defaults to the LOKI_API_KEY env var")
    parser.add_argument(
        "--workdir",
        default="loki_workspace",
        help="where generated code runs (default: ./loki_workspace)",
    )
    parser.add_argument(
        "--skills-file",
        default="loki_workspace/skills.json",
        help="path to the skill library JSON file",
    )
    parser.add_argument(
        "--memory-file",
        default="loki_workspace/memory.jsonl",
        help="path to the experience memory JSONL file",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="where run reports are saved (default: ./runs)",
    )
    parser.add_argument("--version", action="version", version=f"loki {__version__}")
    return parser.parse_args(argv)


def create_agent(args: argparse.Namespace, narrator=None) -> Agent:
    """Build an Agent from CLI args. Raises ValueError when no API key is available."""
    api_key = args.api_key or os.environ.get("LOKI_API_KEY")
    if not api_key:
        raise ValueError(
            "No API key found. Set the LOKI_API_KEY environment variable or pass --api-key.\n"
            "Loki needs your own LLM key (any OpenAI-compatible endpoint) to think with."
        )
    llm = LLMClient(api_key=api_key, model=args.model, base_url=args.base_url)
    skills = SkillLibrary(args.skills_file)
    skills.ensure_seed()
    memory = ExperienceMemory(args.memory_file)
    memory.ensure_seed()
    config = AgentConfig(max_iters=args.max_iters, timeout=args.timeout)
    return Agent(llm=llm, workdir=args.workdir, skills=skills, memory=memory, config=config,
                narrator=narrator)


def save_report(report: RunReport, runs_dir: str | Path) -> Path:
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = runs_dir / f"{stamp}.md"
    path.write_text(report.to_markdown() + "\n", encoding="utf-8")
    return path


def run_cli(args: argparse.Namespace, narrator=None, agent: Agent | None = None) -> int:
    """Run one goal end-to-end. Returns a process exit code."""
    say = narrator or (lambda msg: print(msg))
    if agent is None:
        agent = create_agent(args, narrator=say)
    report = agent.run(args.goal)
    path = save_report(report, args.runs_dir)
    say("")
    if report.success:
        say(f"Timeline secured. Report filed at {path} 🗂️")
        return 0
    say(f"Timeline inconclusive — but the archives are richer. Report filed at {path} 🗂️")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_cli(args)
    except ValueError as exc:
        print(f"loki: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
