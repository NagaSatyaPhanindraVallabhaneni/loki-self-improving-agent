"""Tests for loki.skills — the persistent skill library."""

import json

import pytest

from loki.skills import SEED_SKILLS, SkillLibrary


def make_library(tmp_path) -> SkillLibrary:
    return SkillLibrary(tmp_path / "skills.json")


def test_save_and_retrieve_skill(tmp_path):
    lib = make_library(tmp_path)
    skill = lib.save_skill("my_skill", "does things", "x = 1")
    assert skill.name == "my_skill"
    assert lib.skills["my_skill"].code == "x = 1"


def test_find_skills_ranks_relevant_first(tmp_path):
    lib = make_library(tmp_path)
    lib.save_skill("read_csv_preview", "Read a CSV file and return its columns", "code-a")
    lib.save_skill("fetch_json", "HTTP GET a URL and return parsed JSON", "code-b")
    results = lib.find_skills("read the csv file and list columns")
    assert results, "expected at least one match"
    assert results[0].name == "read_csv_preview"


def test_find_skills_no_overlap_returns_empty(tmp_path):
    lib = make_library(tmp_path)
    lib.save_skill("extract_emails", "find email addresses in text", "code")
    assert lib.find_skills("quantum banana teleportation") == []


def test_find_skills_empty_query_returns_empty(tmp_path):
    lib = make_library(tmp_path)
    lib.save_skill("extract_emails", "find email addresses in text", "code")
    assert lib.find_skills("") == []


def test_find_skills_respects_top_k(tmp_path):
    lib = make_library(tmp_path)
    for i in range(6):
        lib.save_skill(f"csv_tool_{i}", "csv file helper", "code")
    assert len(lib.find_skills("csv file", top_k=2)) == 2


def test_record_use_increments_counter(tmp_path):
    lib = make_library(tmp_path)
    lib.save_skill("counter_skill", "counts", "code")
    lib.record_use("counter_skill")
    lib.record_use("counter_skill")
    assert lib.skills["counter_skill"].uses == 2


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "skills.json"
    lib = SkillLibrary(path)
    lib.save_skill("persist_me", "survives reload", "print('hi')")
    lib.record_use("persist_me")
    lib2 = SkillLibrary(path)
    assert "persist_me" in lib2.skills
    assert lib2.skills["persist_me"].code == "print('hi')"
    assert lib2.skills["persist_me"].uses == 1


def test_ensure_seed_adds_starter_skills_once(tmp_path):
    lib = make_library(tmp_path)
    added = lib.ensure_seed()
    assert added == len(SEED_SKILLS)
    assert lib.ensure_seed() == 0  # idempotent
    assert len(lib.skills) == len(SEED_SKILLS)


def test_invalid_skill_name_rejected(tmp_path):
    lib = make_library(tmp_path)
    with pytest.raises(ValueError):
        lib.save_skill("Not A Valid Name!", "bad", "code")


def test_empty_code_rejected(tmp_path):
    lib = make_library(tmp_path)
    with pytest.raises(ValueError):
        lib.save_skill("empty_skill", "nothing", "   ")


def test_duplicate_save_updates_code_but_keeps_history(tmp_path):
    lib = make_library(tmp_path)
    first = lib.save_skill("evolving", "v1", "code-v1")
    created = first.created_at
    lib.record_use("evolving")
    second = lib.save_skill("evolving", "v2", "code-v2")
    assert second.code == "code-v2"
    assert second.description == "v2"
    assert second.created_at == created
    assert second.uses == 1


def test_skill_file_is_valid_json(tmp_path):
    path = tmp_path / "skills.json"
    lib = SkillLibrary(path)
    lib.save_skill("json_check", "desc", "code")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["name"] == "json_check"


def test_name_is_normalized_to_lowercase(tmp_path):
    lib = make_library(tmp_path)
    skill = lib.save_skill("MixedCase", "desc", "code")
    assert skill.name == "mixedcase"
