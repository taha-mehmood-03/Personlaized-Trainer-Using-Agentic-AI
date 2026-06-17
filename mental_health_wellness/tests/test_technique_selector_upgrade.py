import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

from mental_health_wellness.tools.technique_tools import (
    _semantic_tier_bonus,
    _semantic_bonus,
    _TECHNIQUE_FAMILY,
    _emotion_fit_bonus,
    recommend_technique,
)
from mental_health_wellness.techniques.emotion_metadata import score_technique_match
from mental_health_wellness.nodes.technique_selector_node import select_technique


def test_semantic_tier_bonus():
    # Verify the rescaled tier-based semantic bonus
    assert _semantic_tier_bonus(0.80) == 1.5
    assert _semantic_tier_bonus(0.70) == 0.8
    assert _semantic_tier_bonus(0.55) == 0.3
    assert _semantic_tier_bonus(0.40) == 0.0
    assert _semantic_tier_bonus(0.20) == -0.5


def test_emotion_fit_bonus_ignores_intensity_metadata():
    technique = _technique(
        "journal",
        "Brain Dump Before Sleep",
        "journaling",
        sub_emotions=["rumination"],
        min_i=0.0,
        max_i=0.2,
    )

    low_intensity_score = _emotion_fit_bonus(
        technique,
        primary_sub_emotion="rumination",
        intensity=0.1,
    )
    high_intensity_score = _emotion_fit_bonus(
        technique,
        primary_sub_emotion="rumination",
        intensity=0.95,
    )

    assert high_intensity_score == low_intensity_score


def test_emotion_fit_bonus_ignores_best_for_contexts_metadata():
    technique = _technique(
        "context-only",
        "Context Only Exercise",
        "journaling",
    )
    technique.bestForContexts = ["loneliness", "social_humiliation"]

    assert _emotion_fit_bonus(
        technique,
        primary_sub_emotion="loneliness",
        detected_contexts=["social_humiliation"],
    ) == 0.0


def test_metadata_match_score_ignores_context_and_intensity():
    baseline = score_technique_match(
        "Box Breathing",
        sub_emotions=["performance_anxiety"],
        contexts=[],
        intensity=0.2,
        category="Breathing",
    )
    with_matching_context_and_different_intensity = score_technique_match(
        "Box Breathing",
        sub_emotions=["performance_anxiety"],
        contexts=["presentation_anxiety"],
        intensity=0.95,
        category="Breathing",
    )

    assert with_matching_context_and_different_intensity == baseline


def _technique(tech_id: str, name: str, category_id: str, sub_emotions: list = None, min_i=0.0, max_i=1.0):
    return SimpleNamespace(
        id=tech_id,
        name=name,
        brief=f"{name} brief",
        description=f"{name} description",
        steps=["step one"],
        categoryId=category_id,
        targetSubEmotions=sub_emotions or [],
        targetSymptoms=[],
        targetBehaviors=[],
        avoidSubEmotions=[],
        avoidSymptoms=[],
        avoidBehaviors=[],
        bestForContexts=[],
        minIntensity=min_i,
        maxIntensity=max_i,
        avgRating=4.5,
        effectiveness=0.8,
        durationMinutes=15,
        difficulty="EASY",
        whyItWorks="...",
        pacingTier="normal",
        deliveryMode="exercise",
        isActive=True,
    )


@pytest.mark.asyncio
async def test_recommend_technique_does_not_filter_categories_by_intensity(monkeypatch):
    class FakeTable:
        def __init__(self, rows):
            self.rows = rows
            self.calls = []

        async def find_many(self, **kwargs):
            self.calls.append(kwargs)
            return self.rows

    technique_table = FakeTable(
        [
            _technique("box", "Box Breathing", "breathing", min_i=0.0, max_i=1.0),
            _technique("thought", "Thought Record", "cbt", min_i=0.0, max_i=1.0),
            _technique("journal", "Brain Dump Before Sleep", "journaling", min_i=0.0, max_i=1.0),
        ]
    )
    fake_prisma = SimpleNamespace(
        techniquecategory=FakeTable(
            [
                SimpleNamespace(id="breathing", name="Breathing"),
                SimpleNamespace(id="cbt", name="CBT"),
                SimpleNamespace(id="journaling", name="Journaling"),
            ]
        ),
        technique=technique_table,
    )

    async def fake_get_prisma_client():
        return fake_prisma

    monkeypatch.setattr(
        "mental_health_wellness.db.client.get_prisma_client",
        fake_get_prisma_client,
    )

    result = await recommend_technique.ainvoke(
        {
            "emotion": "fear",
            "intensity": 0.9,
            "user_id": "",
        }
    )

    first_fetch = technique_table.calls[0]
    assert "categoryId" not in first_fetch["where"]
    assert {item["category"] for item in result} == {"Breathing", "CBT", "Journaling"}


@pytest.mark.asyncio
async def test_recommend_technique_can_return_semantic_shortlist(monkeypatch):
    class FakeTable:
        def __init__(self, rows):
            self.rows = rows

        async def find_many(self, **kwargs):
            return self.rows

    techniques = [
        _technique(f"tech-{idx}", f"Technique {idx}", "breathing")
        for idx in range(6)
    ]
    fake_prisma = SimpleNamespace(
        techniquecategory=FakeTable([SimpleNamespace(id="breathing", name="Breathing")]),
        technique=FakeTable(techniques),
    )

    async def fake_get_prisma_client():
        return fake_prisma

    monkeypatch.setattr(
        "mental_health_wellness.db.client.get_prisma_client",
        fake_get_prisma_client,
    )

    result = await recommend_technique.ainvoke(
        {
            "emotion": "anxiety",
            "user_id": "",
            "limit": 5,
        }
    )

    assert len(result) == 5


@pytest.mark.asyncio
async def test_select_technique_context_sufficiency_gate():
    # If context_sufficiency < 0.65 and there is no direct request/action signal, selection is skipped.
    state = {
        "needs_technique": True,
        "context_sufficiency": 0.50,
        "intent": "sharing_distress",
        "gate_route": "technique_pitch",
        "conversation_stage": "ACTION",
        "conversation_strategy": "provide_technique",
        "messages": [],
    }
    res = await select_technique(state)
    # technique_area/technique_plan_mode/technique_series were added to the
    # skip-path payload by the v12.0/v13.0 technique-area + series-plan work,
    # so the empty-selection contract now carries them through too.
    assert res == {
        "recommended_technique": {},
        "recommended_techniques_by_category": {},
        "alternative_techniques": [],
        "technique_area": [],
        "technique_plan_mode": "single",
        "technique_series": [],
    }

    # Bypassed by high context sufficiency
    from unittest.mock import patch
    
    dummy_result = [
        {"name": "Box Breathing", "category": "Breathing", "score_reasons": []}
    ]
    
    class MockTool:
        async def ainvoke(self, *args, **kwargs):
            return dummy_result
            
    mock_tool = MockTool()
    
    with patch("mental_health_wellness.nodes.technique_selector_node.recommend_technique", new=mock_tool):
        # Bypassed by high context sufficiency (0.75 >= 0.65)
        state = {
            "needs_technique": True,
            "context_sufficiency": 0.75,
            "intent": "sharing_distress",
            "gate_route": "technique_pitch",
            "conversation_stage": "ACTION",
            "conversation_strategy": "provide_technique",
            "messages": [],
        }
        res = await select_technique(state)
        assert res["recommended_technique"]["name"] == "Box Breathing"

        # Bypassed by direct technique request intent (regardless of low sufficiency)
        state = {
            "needs_technique": True,
            "context_sufficiency": 0.20,
            "intent": "technique_request",
            "gate_route": "technique_pitch",
            "conversation_stage": "ACTION",
            "conversation_strategy": "provide_technique",
            "messages": [],
        }
        res = await select_technique(state)
        assert res["recommended_technique"]["name"] == "Box Breathing"
