import json
from datetime import UTC, datetime

from conductai.config import load_config
from conductai.data import OperationalRepository
from conductai.observability import EventLedger
from conductai.observability.replay import read_events
from conductai.runtime.q01_selector import Q01Selector


def _run_selector(project_root, tmp_path):
    config = load_config(project_root)
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    repository = OperationalRepository(project_root / "data" / "generated" / "conduct.sqlite", ledger)
    selector = Q01Selector(project_root, config, repository, ledger)
    selection = selector.run(
        run_id="RUN-Q01-TEST", review_id="REV-2026-Q01", virtual_now=datetime(2026, 11, 16, 15, tzinfo=UTC),
    )
    return selection, ledger, path


def test_q01_population_matches_ground_truth_window(project_root, tmp_path):
    selection, ledger, path = _run_selector(project_root, tmp_path)
    gold = json.loads((project_root / "data/generated/ground_truth/Q01_sweep.json").read_text())
    assert selection.population_count == gold["population_count"] == 546
    assert selection.capacity == 40
    assert selection.risk_capacity == 36
    assert selection.random_capacity == 4
    assert selection.seed == 20261116
    assert len(selection.risk_ranked_picks) == 36
    assert len(selection.random_stratified_picks) == 4
    assert len(selection.selected_reviews) == 40
    assert len(set(selection.selected_reviews)) == 40  # no duplicate between risk and random picks


def test_q01_achieves_required_recall_using_only_permitted_signals(project_root, tmp_path):
    selection, ledger, path = _run_selector(project_root, tmp_path)
    gold = json.loads((project_root / "data/generated/ground_truth/Q01_sweep.json").read_text())
    gold_positive = set(gold["gold_positive_ids"])
    picked = set(selection.risk_ranked_picks)
    recall = len(gold_positive & picked) / len(gold_positive)
    assert recall >= 0.70
    # No candidate feature dict carries any prohibited signal.
    prohibited = {"age", "birth_year", "language", "accent", "asr_confidence", "site", "demographics"}
    for candidate in selection.candidates:
        assert prohibited.isdisjoint(candidate.features)
    events = ledger.events("RUN-Q01-TEST")
    fairness = next(event for event in events if event.type.value == "fairness_check")
    assert fairness.payload["passed"] is True
    assert set(fairness.payload["prohibited_features"]) == prohibited


def test_q01_random_slice_is_reproducible_and_disjoint_from_risk_picks(project_root, tmp_path):
    selection_a, _, _ = _run_selector(project_root, tmp_path)
    selection_b, _, _ = _run_selector(project_root, tmp_path / "second")
    assert selection_a.random_stratified_picks == selection_b.random_stratified_picks
    assert set(selection_a.random_stratified_picks).isdisjoint(selection_a.risk_ranked_picks)


def test_q01_transparency_reconciles(project_root, tmp_path):
    selection, ledger, path = _run_selector(project_root, tmp_path)
    events = ledger.events("RUN-Q01-TEST")
    assert events[-1].type.value == "termination"
    assert [event.ts_virtual for event in events] == sorted(event.ts_virtual for event in events)
    assert ledger.verify_chain("RUN-Q01-TEST")
    assert ledger.selection("RUN-Q01-TEST") == selection.model_dump(mode="json")
    recorded_seq = next(event.seq for event in events if event.type.value == "selection_recorded")
    visible_refs = {ref for event in events if event.seq < recorded_seq for ref in event.refs}
    for link in selection.field_provenance.values():
        assert link.event_seqs and max(link.event_seqs) < recorded_seq
        assert link.source_refs and set(link.source_refs) <= visible_refs
    replayed = read_events(path, "RUN-Q01-TEST", event_type="selection_recorded")
    assert replayed and replayed[-1].seq == recorded_seq
