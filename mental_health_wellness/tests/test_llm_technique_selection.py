from mental_health_wellness.nodes.optimized_response_generator import (
    _candidate_by_selected_id,
    _clean_final_response,
    _extract_selected_technique_id,
    _valid_technique_candidates,
)


def test_selected_technique_marker_is_parsed_and_stripped():
    raw = "SELECTED_TECHNIQUE_ID: ex-2\nLet's try Thought Defusion for this."

    assert _extract_selected_technique_id(raw) == "ex-2"
    assert _clean_final_response(raw) == "Let's try Thought Defusion for this."


def test_selected_technique_id_must_match_candidate():
    candidates = _valid_technique_candidates(
        [
            {"id": "ex-1", "name": "Box Breathing"},
            {"id": "ex-2", "name": "Thought Defusion"},
            {"id": "missing-name"},
        ]
    )

    assert len(candidates) == 2
    assert _candidate_by_selected_id(candidates, "ex-2")["name"] == "Thought Defusion"
    assert _candidate_by_selected_id(candidates, "not-real") == {}
