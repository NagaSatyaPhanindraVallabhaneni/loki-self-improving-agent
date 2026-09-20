"""Tests for loki.agent — the self-improvement loop with a fully mocked LLM.

No network, no real LLM: FakeLLM replays scripted replies in order, so every
code path of the loop is exercised deterministically.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from loki.agent import Agent, AgentConfig, RunReport, extract_code
from loki.memory import ExperienceMemory
from loki.skills import SkillLibrary

PLAN_OK = """Plan: print a greeting, nothing fancy.

```python
print("hello from timeline 616")
```
"""

PLAN_BROKEN = """Plan: this will crash on purpose.

```python
raise RuntimeError("pruned on purpose")
```
"""

PLAN_FIXED = """The fix: just print instead of raising.

```python
print("fixed timeline")
```
"""

SKILL_JSON = json.dumps(
    {
        "name": "greet_printer",
        "description": "Print a greeting to stdout.",
        "code": "def greet_printer(msg):\n    print(msg)\n",
    }
)

LESSON_JSON = json.dumps(
    {
        "what_worked": "printing the answer to stdout",
        "what_failed": "nothing on the first attempt",
        "lesson": "keep first attempts tiny and observable",
    }
)

LESSON_JSON_FAIL = json.dumps(
    {
        "what_worked": "the retry loop kept going",
        "what_failed": "every attempt raised the same error",
        "lesson": "read the traceback before retrying the same shape of code",
    }
)


class FakeLLM:
    """Replays scripted replies in call order; records prompts for assertions."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[str] = []

    def chat(self, messages, temperature=0.2):
        self.prompts.append(messages[-1]["content"])
        assert self.replies, "FakeLLM ran out of scripted replies"
        return self.replies.pop(0)


@pytest.fixture()
def agent_factory(tmp_path: Path):
    """Returns a helper that builds an Agent backed by tmp dirs and a FakeLLM."""

    def _make(replies: list[str], max_iters: int = 5, seed_skills: bool = False):
        skills = SkillLibrary(tmp_path / "skills.json")
        if seed_skills:
            skills.ensure_seed()
        memory = ExperienceMemory(tmp_path / "memory.jsonl")
        llm = FakeLLM(replies)
        agent = Agent(
            llm=llm,
            workdir=tmp_path / "work",
            skills=skills,
            memory=memory,
            config=AgentConfig(max_iters=max_iters, timeout=5.0),
            narrator=lambda msg: None,
        )
        return agent, skills, memory, llm

    return _make


def test_success_on_first_try(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_OK, SKILL_JSON, LESSON_JSON])
    report = agent.run("print a greeting")
    assert isinstance(report, RunReport)
    assert report.success
    assert report.iterations == 1
    assert "hello from timeline 616" in report.final_output


def test_extract_code_pulls_fenced_block():
    assert extract_code(PLAN_OK) == 'print("hello from timeline 616")'


def test_extract_code_falls_back_to_whole_reply():
    assert extract_code("print('no fence here')") == "print('no fence here')"


def test_fail_then_fix_succeeds_on_second_attempt(agent_factory):
    agent, _, _, llm = agent_factory([PLAN_BROKEN, PLAN_FIXED, SKILL_JSON, LESSON_JSON])
    report = agent.run("print something")
    assert report.success
    assert report.iterations == 2
    assert "fixed timeline" in report.final_output
    assert any("[loki:fix]" in p for p in llm.prompts)


def test_max_iters_exhaustion_reports_failure(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_BROKEN, PLAN_BROKEN, LESSON_JSON_FAIL], max_iters=2)
    report = agent.run("do the impossible")
    assert not report.success
    assert report.iterations == 2


def test_skill_saved_on_success(agent_factory):
    agent, skills, _, _ = agent_factory([PLAN_OK, SKILL_JSON, LESSON_JSON])
    report = agent.run("print a greeting")
    assert report.skills_added == ["greet_printer"]
    assert "greet_printer" in skills.skills


def test_lesson_saved_on_success(agent_factory):
    agent, _, memory, _ = agent_factory([PLAN_OK, SKILL_JSON, LESSON_JSON])
    report = agent.run("print a greeting")
    assert report.lessons_added == ["keep first attempts tiny and observable"]
    assert len(memory.entries) == 1


def test_lesson_saved_on_failure_too(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_BROKEN, LESSON_JSON_FAIL], max_iters=1)
    report = agent.run("do the impossible")
    assert not report.success
    assert report.skills_added == []
    assert len(report.lessons_added) == 1
    assert "traceback" in report.lessons_added[0]


def test_bad_skill_json_does_not_break_run(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_OK, "not json at all", LESSON_JSON])
    report = agent.run("print a greeting")
    assert report.success
    assert report.skills_added == []


def test_report_markdown_contains_key_sections(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_OK, SKILL_JSON, LESSON_JSON])
    md = agent.run("print a greeting").to_markdown()
    assert "print a greeting" in md
    assert "✅ SUCCESS" in md
    assert "Attempt 1" in md
    assert 'print("hello from timeline 616")' in md
    assert "greet_printer" in md


def test_report_markdown_marks_failure(agent_factory):
    agent, _, _, _ = agent_factory([PLAN_BROKEN, LESSON_JSON_FAIL], max_iters=1)
    assert "❌ INCOMPLETE" in agent.run("do the impossible").to_markdown()


def test_relevant_skill_is_retrieved_and_use_recorded(agent_factory):
    agent, skills, _, _ = agent_factory([PLAN_OK, SKILL_JSON, LESSON_JSON])
    skills.save_skill("csv_reader", "Read a CSV file and return rows", "code")
    agent.run("read a csv file")
    assert skills.skills["csv_reader"].uses == 1


def test_empty_goal_rejected(agent_factory):
    agent, _, _, _ = agent_factory([])
    with pytest.raises(ValueError):
        agent.run("   ")


def test_config_validation():
    with pytest.raises(ValidationError):
        AgentConfig(max_iters=0)
    with pytest.raises(ValidationError):
        AgentConfig(max_iters=21)
    with pytest.raises(ValidationError):
        AgentConfig(timeout=-1)
