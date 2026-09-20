"""Tests for loki.sandbox — real subprocess execution, no mocks needed."""

from loki.sandbox import ExecutionResult, run_code


def test_success_captures_stdout(tmp_path):
    result = run_code("print('hello timeline')", tmp_path)
    assert isinstance(result, ExecutionResult)
    assert result.succeeded
    assert result.stdout.strip() == "hello timeline"
    assert result.exit_code == 0
    assert not result.timed_out


def test_stderr_captured_on_crash(tmp_path):
    result = run_code("raise ValueError('pruned!')", tmp_path)
    assert not result.succeeded
    assert result.exit_code != 0
    assert "ValueError" in result.stderr
    assert "pruned!" in result.stderr


def test_nonzero_exit_code(tmp_path):
    result = run_code("import sys; sys.exit(3)", tmp_path)
    assert not result.succeeded
    assert result.exit_code == 3


def test_timeout_kills_long_running_code(tmp_path):
    result = run_code("import time; time.sleep(30)", tmp_path, timeout=1.0)
    assert result.timed_out
    assert not result.succeeded
    assert result.exit_code == -1
    assert "TIMEOUT" in result.stderr
    assert result.elapsed_s < 10


def test_script_file_written_to_workdir(tmp_path):
    run_code("print(1)", tmp_path, filename="my_attempt.py")
    assert (tmp_path / "my_attempt.py").exists()


def test_code_runs_with_workdir_as_cwd(tmp_path):
    result = run_code("import os; print(os.path.basename(os.getcwd()))", tmp_path)
    assert result.succeeded
    assert result.stdout.strip() == tmp_path.name


def test_elapsed_time_recorded(tmp_path):
    result = run_code("print('fast')", tmp_path)
    assert result.elapsed_s >= 0
    assert result.elapsed_s < 30


def test_multiline_output_preserved(tmp_path):
    result = run_code("print('a'); print('b'); print('c')", tmp_path)
    assert result.stdout.split() == ["a", "b", "c"]


def test_workdir_created_if_missing(tmp_path):
    nested = tmp_path / "deep" / "nested"
    result = run_code("print('ok')", nested)
    assert result.succeeded
    assert nested.exists()
