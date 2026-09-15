from conductai.observability.events import EventType


def test_v1_catalog_has_exactly_79_unique_types():
    assert len(EventType) == 79
    assert len({event.value for event in EventType}) == 79
