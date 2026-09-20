"""Tests for loki.memory — the append-only experience log."""

import json

from loki.memory import Experience, ExperienceMemory


def make_memory(tmp_path) -> ExperienceMemory:
    return ExperienceMemory(tmp_path / "memory.jsonl")


def log_sample(memory: ExperienceMemory) -> Experience:
    return memory.log(
        task="average the price column of a csv",
        what_worked="used csv.DictReader and printed headers first",
        what_failed="assumed the column was named 'cost'",
        lesson="always inspect CSV headers before assuming column names",
    )


def test_log_appends_experience(tmp_path):
    memory = make_memory(tmp_path)
    entry = log_sample(memory)
    assert entry.task.startswith("average the price")
    assert len(memory.entries) == 1


def test_retrieve_finds_relevant_lesson(tmp_path):
    memory = make_memory(tmp_path)
    log_sample(memory)
    memory.log(
        task="fetch a web page",
        what_worked="used httpx with a timeout",
        what_failed="forgot the timeout once",
        lesson="always set timeouts on network calls",
    )
    results = memory.retrieve("csv column headers price")
    assert results, "expected at least one match"
    assert "headers" in results[0].lesson


def test_retrieve_no_match_returns_empty(tmp_path):
    memory = make_memory(tmp_path)
    log_sample(memory)
    assert memory.retrieve("quantum banana teleportation") == []


def test_retrieve_respects_top_k(tmp_path):
    memory = make_memory(tmp_path)
    for i in range(5):
        memory.log(task=f"csv task {i}", what_worked="w", what_failed="f", lesson="csv lesson")
    assert len(memory.retrieve("csv", top_k=2)) == 2


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "memory.jsonl"
    memory = ExperienceMemory(path)
    log_sample(memory)
    memory2 = ExperienceMemory(path)
    assert len(memory2.entries) == 1
    assert memory2.entries[0].lesson.startswith("always inspect")


def test_memory_file_is_jsonl(tmp_path):
    path = tmp_path / "memory.jsonl"
    memory = ExperienceMemory(path)
    log_sample(memory)
    log_sample(memory)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_ensure_seed_on_empty_memory(tmp_path):
    memory = make_memory(tmp_path)
    assert memory.ensure_seed() == 1
    assert memory.ensure_seed() == 0  # idempotent
    assert len(memory.entries) == 1


def test_ensure_seed_keeps_existing_entries(tmp_path):
    memory = make_memory(tmp_path)
    log_sample(memory)
    assert memory.ensure_seed() == 0
    assert len(memory.entries) == 1
