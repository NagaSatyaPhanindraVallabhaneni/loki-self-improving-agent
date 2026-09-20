"""The self-improvement loop: plan -> code -> execute -> reflect -> grow.

Given a goal, Loki:
  1. retrieves relevant skills + past lessons,
  2. asks the LLM for a plan and a first attempt at code,
  3. runs the code in the sandbox and captures the result,
  4. on failure, feeds the error back to the LLM and retries,
  5. on success (or final failure), distills a reusable skill and a lesson
     into the library and memory, so the *next* run starts smarter.

Status messages are delivered in a playful TVA-clerk voice — original
quips, not quotes from any show.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .llm import LLMClient
from .memory import ExperienceMemory
from .sandbox import ExecutionResult, run_code
from .skills import Skill, SkillLibrary

_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# --- persona voice -----------------------------------------------------------

QUIPS = {
    "start": "Howdy! Loki here — let's see what timeline this task takes us down. 🌀",
    "skills_found": "Dusted off {n} skill(s) from the archives that might help: {names}.",
    "lessons_found": "Found {n} lesson(s) from past variants. Somebody learned these the hard way.",
    "planning": "Alright, I've got a plan cookin'. Writin' up the first attempt now…",
    "attempt": "Spinnin' up the sandbox — attempt {i} of {n}. Let's see if this timeline holds…",
    "failed": "Well, butter my biscuit — that timeline just pruned itself. Here's the damage:",
    "retry": "Variant located! Takin' another crack at it…",
    "success": "Hot dog, that worked! Filing this one away in the archives…",
    "skill_saved": "New skill filed under '{name}'. The archives grow! 📚",
    "skill_skipped": "Couldn't distill a clean skill from that one — movin' on.",
    "lesson_saved": "Lesson logged for future variants. They'll thank me later.",
    "exhausted": "Well, that's all the timeline branches I've got. Logging what I learned anyway.",
}


# --- prompts -----------------------------------------------------------------

SYSTEM_PROMPT = """You are LOKI, a resourceful coding assistant who solves tasks by writing
and running real Python code. You think in timelines: every attempt is a branch,
and failures just prune bad branches.

Rules for your replies:
- When asked for code, put the ENTIRE runnable script in ONE ```python fenced block.
- The code runs as a script (python attempt_N.py) in an empty working directory.
- Only use the Python standard library plus: httpx, pydantic, numpy (if installed).
- Print your final answer with print() so it appears in stdout.
- Keep scripts self-contained: no input(), no GUIs, no infinite loops, no network
  calls except plain HTTP(S) GET/POST via httpx.
- When asked for JSON, reply with ONLY the JSON object, no prose."""


def _skills_section(skills: list[Skill]) -> str:
    if not skills:
        return "No relevant skills in the library yet — you're blazing a fresh trail."
    parts = []
    for skill in skills:
        parts.append(f"### Skill: {skill.name}\n{skill.description}\n```python\n{skill.code}\n```")
    return "\n\n".join(parts)


def _lessons_section(lessons: list) -> str:
    if not lessons:
        return "No past lessons on file yet."
    return "\n".join(f"- {lesson.lesson} (from: {lesson.task})" for lesson in lessons)


def build_initial_prompt(goal: str, skills: list[Skill], lessons: list) -> str:
    return f"""[loki:plan]
GOAL: {goal}

Relevant skills from your library (reuse these ideas freely):
{_skills_section(skills)}

Lessons learned by past variants:
{_lessons_section(lessons)}

First, write 2-4 sentences of plan. Then give the complete runnable Python script
in ONE ```python fenced block. Remember to print the final answer."""


def build_fix_prompt(goal: str, code: str, result: ExecutionResult) -> str:
    detail = result.stderr.strip() or f"(exit code {result.exit_code}, no stderr)"
    if result.timed_out:
        detail = f"TIMEOUT after {result.elapsed_s}s. " + detail
    return f"""[loki:fix]
GOAL: {goal}

Your last attempt failed. Here is the code you wrote:
```python
{code}
```
And here is what happened when it ran (stdout was: {result.stdout.strip()!r}):
```
{detail}
```
Diagnose the problem in one or two sentences, then give the corrected complete
script in ONE ```python fenced block."""


def build_skill_prompt(goal: str, code: str) -> str:
    return f"""[loki:skill]
GOAL (completed): {goal}

The working solution:
```python
{code}
```
Distill the most reusable function or pattern from this solution into a library
skill. Reply with ONLY this JSON:
{{"name": "snake_case_name", "description": "one sentence: what it does",
  "code": "the standalone reusable code"}}"""


def build_lesson_prompt(goal: str, attempts: list[Attempt], success: bool) -> str:
    outcome = "SUCCEEDED" if success else "FAILED after all attempts"
    summary = "\n".join(
        f"- attempt {a.iteration}: exit={a.result.exit_code} "
        f"timed_out={a.result.timed_out} stderr={a.result.stderr.strip()[:200]!r}"
        for a in attempts
    )
    return f"""[loki:lesson]
GOAL: {goal}
OUTCOME: {outcome}
ATTEMPT LOG:
{summary}
Write down what this run taught us. Reply with ONLY this JSON:
{{"what_worked": "one sentence", "what_failed": "one sentence",
  "lesson": "one actionable sentence a future variant should remember"}}"""


def extract_code(response: str) -> str:
    """Pull the ```python fenced block out of an LLM reply.

    Falls back to the whole reply (stripped) when no fence is present, so a
    chatty model that forgot the fence doesn't stall the loop.
    """
    match = _CODE_FENCE_RE.search(response)
    if match:
        return match.group(1).strip()
    return response.strip()


# --- config / report ----------------------------------------------------------


class AgentConfig(BaseModel):
    """Validated knobs for one agent run."""

    max_iters: int = Field(default=5, ge=1, le=20)
    timeout: float = Field(default=30.0, gt=0, le=600)


@dataclass
class Attempt:
    iteration: int
    code: str
    result: ExecutionResult


@dataclass
class RunReport:
    goal: str
    success: bool
    iterations: int
    final_code: str
    final_output: str
    attempts: list[Attempt] = field(default_factory=list)
    skills_added: list[str] = field(default_factory=list)
    lessons_added: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""

    def to_markdown(self) -> str:
        status = "✅ SUCCESS" if self.success else "❌ INCOMPLETE"
        lines = [
            f"# Loki run report — {status}",
            "",
            f"**Goal:** {self.goal}",
            f"**Started:** {self.started_at}  ",
            f"**Ended:** {self.ended_at}  ",
            f"**Iterations used:** {self.iterations}",
            "",
        ]
        for attempt in self.attempts:
            r = attempt.result
            icon = "✅" if r.succeeded else "⏱️" if r.timed_out else "❌"
            lines += [
                f"## Attempt {attempt.iteration} {icon}",
                "",
                f"*exit_code={r.exit_code}, timed_out={r.timed_out}, elapsed={r.elapsed_s}s*",
                "",
                "```python",
                attempt.code,
                "```",
                "",
                "<details><summary>output</summary>",
                "",
                "```",
                f"--- stdout ---\n{r.stdout.strip() or '(empty)'}",
                f"--- stderr ---\n{r.stderr.strip() or '(empty)'}",
                "```",
                "",
                "</details>",
                "",
            ]
        if self.skills_added:
            lines += ["## Skills added to the library", ""]
            lines += [f"- `{name}`" for name in self.skills_added] + [""]
        if self.lessons_added:
            lines += ["## Lessons logged", ""]
            lines += [f"- {lesson}" for lesson in self.lessons_added] + [""]
        return "\n".join(lines)


# --- the agent ----------------------------------------------------------------


class Agent:
    """Runs the plan -> code -> execute -> reflect loop for a goal."""

    def __init__(
        self,
        llm: LLMClient,
        workdir: str | Path,
        skills: SkillLibrary,
        memory: ExperienceMemory,
        config: AgentConfig | None = None,
        narrator: Callable[[str], None] | None = None,
    ) -> None:
        self.llm = llm
        self.workdir = Path(workdir)
        self.skills = skills
        self.memory = memory
        self.config = config or AgentConfig()
        self._say = narrator or (lambda msg: print(msg))

    def _parse_json_reply(self, reply: str) -> dict | None:
        """Extract a JSON object from an LLM reply, tolerating fences and prose."""
        text = reply.strip()
        match = _JSON_FENCE_RE.search(text)
        if match:
            text = match.group(1)
        try:
            parsed = json.loads(text.strip())
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _distill_skill(self, goal: str, code: str) -> list[str]:
        try:
            reply = self.llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_skill_prompt(goal, code)},
                ]
            )
        except Exception as exc:  # noqa: BLE001 - a failed distillation must not fail the run
            self._say(f"{QUIPS['skill_skipped']} ({type(exc).__name__})")
            return []
        data = self._parse_json_reply(reply)
        if not data or not data.get("name") or not data.get("code"):
            self._say(QUIPS["skill_skipped"])
            return []
        try:
            skill = self.skills.save_skill(
                name=str(data["name"]),
                description=str(data.get("description", "")),
                code=str(data["code"]),
            )
        except ValueError:
            self._say(QUIPS["skill_skipped"])
            return []
        self._say(QUIPS["skill_saved"].format(name=skill.name))
        return [skill.name]

    def _distill_lesson(self, goal: str, attempts: list[Attempt], success: bool) -> list[str]:
        try:
            reply = self.llm.chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_lesson_prompt(goal, attempts, success)},
                ]
            )
        except Exception as exc:  # noqa: BLE001 - a failed distillation must not fail the run
            self._say(f"No lesson this time ({type(exc).__name__}).")
            return []
        data = self._parse_json_reply(reply)
        if not data or not data.get("lesson"):
            return []
        entry = self.memory.log(
            task=goal,
            what_worked=str(data.get("what_worked", "")),
            what_failed=str(data.get("what_failed", "")),
            lesson=str(data["lesson"]),
        )
        self._say(QUIPS["lesson_saved"])
        return [entry.lesson]

    def run(self, goal: str) -> RunReport:
        """Execute the self-improvement loop for *goal* and return a report."""
        goal = goal.strip()
        if not goal:
            raise ValueError("goal must not be empty")
        started_at = _utcnow()
        run_dir = self.workdir / f"run_{_timestamp()}"
        self.workdir.mkdir(parents=True, exist_ok=True)

        self._say(QUIPS["start"])
        self._say(f'Goal for this timeline: "{goal}"')

        relevant = self.skills.find_skills(goal, top_k=3)
        if relevant:
            names = ", ".join(f"`{s.name}`" for s in relevant)
            self._say(QUIPS["skills_found"].format(n=len(relevant), names=names))
            for skill in relevant:
                self.skills.record_use(skill.name)

        lessons = self.memory.retrieve(goal, top_k=3)
        if lessons:
            self._say(QUIPS["lessons_found"].format(n=len(lessons)))

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_initial_prompt(goal, relevant, lessons)},
        ]

        attempts: list[Attempt] = []
        final_code = ""
        success = False

        self._say(QUIPS["planning"])
        for i in range(1, self.config.max_iters + 1):
            self._say(QUIPS["attempt"].format(i=i, n=self.config.max_iters))
            reply = self.llm.chat(messages)
            code = extract_code(reply)
            final_code = code
            result = run_code(
                code, run_dir, filename=f"attempt_{i}.py", timeout=self.config.timeout
            )
            attempts.append(Attempt(iteration=i, code=code, result=result))

            if result.succeeded:
                success = True
                self._say(QUIPS["success"])
                if result.stdout.strip():
                    self._say(f"Output:\n{result.stdout.strip()}")
                break

            self._say(QUIPS["failed"])
            detail = result.stderr.strip() or f"(exit code {result.exit_code})"
            self._say(detail[:500])
            if i < self.config.max_iters:
                self._say(QUIPS["retry"])
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": build_fix_prompt(goal, code, result)})

        skills_added: list[str] = []
        lessons_added: list[str] = []
        if success:
            skills_added = self._distill_skill(goal, final_code)
        else:
            self._say(QUIPS["exhausted"])
        lessons_added = self._distill_lesson(goal, attempts, success)

        last_output = attempts[-1].result.stdout.strip() if attempts else ""
        return RunReport(
            goal=goal,
            success=success,
            iterations=len(attempts),
            final_code=final_code,
            final_output=last_output,
            attempts=attempts,
            skills_added=skills_added,
            lessons_added=lessons_added,
            started_at=started_at,
            ended_at=_utcnow(),
        )
