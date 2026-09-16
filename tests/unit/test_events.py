from conductai.observability.events import EventType


def test_v1_catalog_has_exactly_80_unique_types():
    # 79 from the Stage 3 architecture blueprint, plus `selection_recorded` (Stage 4F): Q01's portfolio
    # selection has no AssessmentRecord shape (no findings, no three outcomes), so it needed its own
    # terminal record-persisted event distinct from `assessment_recorded`, added and documented in the
    # handoff rather than silently overloading `assessment_recorded` for a different record shape.
    assert len(EventType) == 80
    assert len({event.value for event in EventType}) == 80
