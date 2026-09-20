"""Tests for the loki CLI (loki.__main__)."""

import argparse

import pytest

import loki.__main__ as cli_main
from loki.agent import RunReport


def test_parse_args_defaults():
    args = cli_main.parse_args(["do a thing"])
    assert args.goal == "do a thing"
    assert args.max_iters == 5
    assert args.timeout == 30.0
    assert args.model == "gpt-4o-mini"
    assert args.runs_dir == "runs"


def test_parse_args_custom_flags():
    args = cli_main.parse_args(
        ["do a thing", "--max-iters", "3", "--model", "llama-3", "--runs-dir", "out"]
    )
    assert args.max_iters == 3
    assert args.model == "llama-3"
    assert args.runs_dir == "out"


def test_missing_api_key_returns_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("LOKI_API_KEY", raising=False)
    code = cli_main.main(["do a thing"])
    assert code == 2
    assert "LOKI_API_KEY" in capsys.readouterr().err


def test_api_key_from_env_is_accepted(monkeypatch):
    monkeypatch.setenv("LOKI_API_KEY", "test-key")
    args = cli_main.parse_args(["do a thing"])
    agent = cli_main.create_agent(args, narrator=lambda msg: None)
    assert agent.llm.model == "gpt-4o-mini"
    assert repr(agent.llm) == (
        "LLMClient(model='gpt-4o-mini', base_url='https://api.openai.com/v1', api_key='***')"
    )


class FakeAgent:
    """Stand-in for Agent so CLI tests never touch the network."""

    def __init__(self, report: RunReport):
        self._report = report

    def run(self, goal: str) -> RunReport:
        assert goal == "count words"
        return self._report


def _report(success: bool) -> RunReport:
    return RunReport(
        goal="count words",
        success=success,
        iterations=1,
        final_code="print('x')",
        final_output="x",
        started_at="t0",
        ended_at="t1",
    )


def test_run_cli_saves_report_and_returns_0(tmp_path):
    args = argparse.Namespace(goal="count words", runs_dir=str(tmp_path / "runs"))
    code = cli_main.run_cli(args, narrator=lambda msg: None, agent=FakeAgent(_report(True)))
    assert code == 0
    saved = list((tmp_path / "runs").glob("*.md"))
    assert len(saved) == 1
    content = saved[0].read_text(encoding="utf-8")
    assert "count words" in content
    assert "✅ SUCCESS" in content


def test_run_cli_returns_1_on_failure(tmp_path):
    args = argparse.Namespace(goal="count words", runs_dir=str(tmp_path / "runs"))
    code = cli_main.run_cli(args, narrator=lambda msg: None, agent=FakeAgent(_report(False)))
    assert code == 1


def test_narrator_receives_progress_messages(tmp_path):
    messages: list[str] = []
    args = argparse.Namespace(goal="count words", runs_dir=str(tmp_path / "runs"))
    cli_main.run_cli(args, narrator=messages.append, agent=FakeAgent(_report(True)))
    assert any("Report filed" in m for m in messages)


def test_main_invalid_max_iters_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("LOKI_API_KEY", "test-key")
    code = cli_main.main(["do a thing", "--max-iters", "0"])
    assert code == 2
    assert "max_iters" in capsys.readouterr().err


def test_env_overrides_for_model_and_base_url(monkeypatch):
    monkeypatch.setenv("LOKI_API_KEY", "k")
    monkeypatch.setenv("LOKI_MODEL", "my-model")
    monkeypatch.setenv("LOKI_BASE_URL", "https://example.com/v1")
    args = cli_main.parse_args(["do a thing"])
    assert args.model == "my-model"
    assert args.base_url == "https://example.com/v1"
    # argparse should also error without a goal
    with pytest.raises(SystemExit):
        cli_main.parse_args([])
