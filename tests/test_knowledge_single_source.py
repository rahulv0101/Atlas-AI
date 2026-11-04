import json
from pathlib import Path

import atlas_ai.brain.nlu as nlu
from atlas_ai.brain.knowledge import BrainKnowledge
from atlas_ai.knowledge_paths import knowledge_root
from atlas_ai.operator_core.knowledge import KnowledgeBase


def test_active_and_compatibility_readers_share_one_root():
    assert BrainKnowledge().root == KnowledgeBase().root == knowledge_root()
    assert not list((Path(__file__).resolve().parents[1] / "atlas_ai" / "knowledge").glob("*.json"))
    risk = BrainKnowledge().load("risk_policy")
    assert risk == KnowledgeBase().load("risk_policy")
    assert "evolved_strategy_promotion" in risk


def test_knowledge_cache_refreshes_and_does_not_leak_nested_mutations(tmp_path):
    path = tmp_path / "market_knowledge.json"
    path.write_text(json.dumps({"concepts": [{"name": "trend", "definition": "first"}]}))
    knowledge = BrainKnowledge(tmp_path)
    first = knowledge.load("market_knowledge")
    first["concepts"][0]["definition"] = "caller mutation"
    assert knowledge.get_market_concept("trend")["definition"] == "first"
    path.write_text(json.dumps({"concepts": [{"name": "trend", "definition": "updated evidence"}]}))
    assert knowledge.get_market_concept("trend")["definition"] == "updated evidence"


def test_missing_explicit_root_never_reads_unrelated_project_knowledge(tmp_path):
    knowledge = BrainKnowledge(tmp_path)
    assert knowledge.load("system_overview") == {}
    (tmp_path / "system_overview.json").write_text('{"identity":"isolated"}')
    assert knowledge.load("system_overview")["identity"] == "isolated"


def test_nlu_examples_do_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(nlu, "_EXAMPLE_CACHE", None)
    assert len(nlu._load_examples()) >= 100


def test_nlu_example_cache_refreshes_when_knowledge_changes(tmp_path, monkeypatch):
    path = tmp_path / "nlu_examples.json"
    path.write_text('[{"text":"first","intent":"general_question"}]')
    monkeypatch.setattr(nlu, "knowledge_root", lambda: tmp_path)
    monkeypatch.setattr(nlu, "_EXAMPLE_CACHE", None)
    assert nlu._load_examples()[0]["text"] == "first"
    path.write_text('[{"text":"updated example","intent":"system_status"}]')
    assert nlu._load_examples()[0]["text"] == "updated example"


def test_macro_writer_and_readers_use_the_canonical_file(tmp_path, monkeypatch):
    import atlas_ai.macro_context_updater as updater
    import atlas_ai.brain.external_context as external
    import atlas_ai.market_context as market
    from datetime import datetime, timezone

    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": [
        {"key": "dxy_alignment", "value": "supports_gold"},
    ]}
    monkeypatch.setattr(updater, "knowledge_root", lambda: tmp_path)
    monkeypatch.setattr(external, "knowledge_root", lambda: tmp_path)
    monkeypatch.setattr(market, "knowledge_root", lambda: tmp_path)
    monkeypatch.setattr(updater, "build_macro_context", lambda: payload)
    updater.write_external_context()
    assert external.load_external_context()["items"] == payload["items"]
    assert market._fresh_external_context_fields()["dxy_alignment"] == "supports_gold"
    assert (tmp_path / "external_context.json").is_file()
