"""User corrections invalidate observations, not the underlying personal method."""
import json

from recall_feedback import augment_query, record_feedback, remember_approved_navigation
from test_feedback_query_hints import QUERY, NAV, CONTEXT, response, seed, prepare


def test_human_invalidates_generic_observation_without_deleting_ledger(tmp_path):
    old = seed(tmp_path, actor="agent", origin="approved_navigation_observed")
    correction = seed(tmp_path, actor="human", outcome="unhelpful",
                      invalidates_feedback_ids=[old["feedback_id"]])
    # Subsequent agent repetition cannot overturn an explicit owner correction.
    seed(tmp_path, actor="agent", outcome="helpful", origin="task_navigation_observed", task_anchors=["Quartz"])
    query, audit = prepare(tmp_path)
    assert query == QUERY and audit["locators"] == []
    assert audit["invalidated_feedback_ids"] == [old["feedback_id"]]
    assert len((tmp_path / "recall-feedback.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    assert correction["invalidates_feedback_ids"] == [old["feedback_id"]]
    assert remember_approved_navigation(tmp_path, project_id="project-a", user_id="user-a",
                                        query=QUERY, response=response(), context=CONTEXT) == []


def test_generic_method_not_auto_learned_but_method_labeled_task_knowledge_is(tmp_path):
    data = response()
    source = data["audit"]["stage_b"]["input_sources"][0]
    source["task_relevance"] = {"kind": "method_request", "task_anchor": "Quartz",
                               "evidence_anchor": "部署入口", "explanation": "泛化原则"}
    assert remember_approved_navigation(tmp_path, project_id="project-a", user_id="user-a",
                                        query=QUERY, response=data, context=CONTEXT) == []
    source["task_relevance"] = {"kind": "task_detail", "task_anchor": "deployment",
                               "evidence_anchor": "部署入口", "explanation": "该组件部署方法中的实际访问配置"}
    ids = remember_approved_navigation(tmp_path, project_id="project-a", user_id="user-a",
                                      query=QUERY, response=data, context=CONTEXT)
    assert len(ids) == 1
    assert NAV in prepare(tmp_path, query="Quartz deployment automation failure，查一下安全访问入口")[1]["locators"]


def test_agent_only_signal_matches_do_not_certify_a_navigation_hint(tmp_path):
    seed(tmp_path, actor="agent", origin="explicit_observation", expected_signals=["Quartz", "automation"])
    assert prepare(tmp_path)[1]["locators"] == []


def test_directory_locators_are_consumable_and_not_fact_admission(tmp_path):
    directory = "d:/work/component/.config/buildTypes/"
    seed(tmp_path, actor="human", outcome="helpful", expected_navigation=[directory])
    query, audit = prepare(tmp_path)
    assert query == QUERY and audit["locators"] == [directory]
    assert audit["fact_admission"] is False and audit["scope_changed"] is False
