"""Unit tests for entity resolution, profile building, and taste strategy.

All Qloo calls are faked; no network or API key is required.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.services.qloo.client import QlooClient
from app.services.qloo import cache
from app.services.qloo.entity_resolver import resolve_entities
from app.services.qloo.profile_builder import build_profile
from app.schemas.taste import TasteEditingStrategy
from app.services import taste_intelligence
from app.services.taste_reel import apply_strategy_to_plan, base_template_for
from app.schemas.editing_plan import EditingPlan, ClipConfig


@pytest.fixture(autouse=True)
def clear_qloo_cache():
    cache.clear_cache()
    yield
    cache.clear_cache()


class FakeQloo(QlooClient):
    def __init__(self, *, entities=None, tags=None, insights=None):
        self._api_key = 'fake'
        self._base_url = 'https://hackathon.api.qloo.com'
        self._entities = entities
        self._tags = tags
        self._insights = insights or {'results': []}

    def search(self, query, *, types=None, take=5, extra=None):
        if self._entities is None:
            return [{'entity_id': f'urn:{query}', 'name': query, 'type': types or 'urn:entity:movie',
                     'popularity': 0.9, 'tags': [{'tag_id': 'urn:tag:scifi', 'name': 'Sci-Fi'}]}]
        return self._entities

    def tags_search(self, query, *, take=10, extra=None):
        if self._tags is None:
            return [{'tag_id': 'urn:tag:' + query.lower(), 'name': query, 'type': 'genre'}]
        return self._tags

    def insights(self, params):
        return self._insights


def test_resolve_entities_and_tags_separate_layers():
    fake = FakeQloo()
    entities, tags, unresolved = resolve_entities([
        {'text': 'Interstellar', 'category': 'movie'},
        {'text': 'Nolan', 'category': 'director'},
        {'text': 'ambient', 'category': 'genre'},
    ], client=fake)
    assert {e.entity_type for e in entities} == {'urn:entity:movie', 'urn:entity:person'}
    assert tags and tags[0].tag_id.startswith('urn:tag:')
    assert unresolved == []


def test_unresolvable_preference_is_reported_not_faked():
    fake = FakeQloo(entities=[])  # search returns nothing
    entities, tags, unresolved = resolve_entities(
        [{'text': 'zzzznotathing', 'category': 'movie'}], client=fake)
    assert entities == []
    assert unresolved and unresolved[0].query == 'zzzznotathing'


def test_build_profile_separates_declared_resolved_and_cultural():
    fake = FakeQloo(insights={'results': [
        {'entity_id': 'urn:dunkirk', 'name': 'Dunkirk', 'affinity': 0.88},
    ]})
    profile = build_profile([{'text': 'Interstellar', 'category': 'movie'}], client=fake, use_qloo=True)
    assert profile.source == 'qloo'
    assert [d.text for d in profile.declared] == ['Interstellar']
    assert any(a.name == 'Dunkirk' for a in profile.cultural_associations)
    # Cultural associations must record what seeded them (auditability).
    assert all(a.derived_from for a in profile.cultural_associations)
    summary = profile.summary()
    assert set(summary) >= {'declared', 'resolved_entities', 'cultural_associations', 'tag_signals'}


def test_declared_only_profile_when_qloo_disabled():
    profile = build_profile([{'text': 'Interstellar', 'category': 'movie'}], use_qloo=False)
    assert profile.source == 'declared_only'
    assert profile.cultural_associations == []


def test_rule_based_strategy_differentiates_by_taste():
    cinematic = taste_intelligence._rule_based_strategy(
        {'declared': [{'text': 'Interstellar'}], 'tag_signals': [{'name': 'Atmospheric Orchestral'}],
         'cultural_associations': [{'name': 'Epic Sci-Fi'}]})
    energetic = taste_intelligence._rule_based_strategy(
        {'declared': [{'text': 'EDM workout'}], 'tag_signals': [{'name': 'High Energy Dance Pop'}],
         'cultural_associations': []})
    assert cinematic.color_mood == 'cinematic' and cinematic.pacing == 'slow'
    assert energetic.pacing == 'fast' and energetic.color_mood == 'vibrant'
    # Strategies cite a basis (no invented facts).
    assert all(r.basis for r in cinematic.reasoning)


def test_strategy_is_validated_against_supported_values():
    # An out-of-range / unsupported value must be rejected by the schema.
    with pytest.raises(Exception):
        TasteEditingStrategy.model_validate({'color_mood': 'not_a_real_mood'})
    with pytest.raises(Exception):
        TasteEditingStrategy.model_validate({'pacing': 'ludicrous_speed'})


def test_llm_strategy_falls_back_on_invalid_output(monkeypatch):
    # If the LLM returns garbage, we must fall back to rules, never crash.
    monkeypatch.setattr(taste_intelligence, 'setting', lambda *a, **k: 'gemini' if a[0] == 'AI_PROVIDER' else 'key')
    monkeypatch.setattr(taste_intelligence, '_llm_available', lambda *_: True)
    monkeypatch.setattr(taste_intelligence, 'generate_plan', lambda messages: {'pacing': 'INVALID'})
    response = taste_intelligence.generate_strategy(
        {'declared': [{'text': 'Interstellar'}], 'tag_signals': [{'name': 'Atmospheric'}],
         'cultural_associations': [], 'resolved_entities': [{'name': 'x'}]})
    assert response.used_llm is False  # fell back
    assert response.strategy.pacing in ('slow', 'balanced', 'fast', 'beat_driven')


def test_apply_strategy_overlays_onto_plan_knobs():
    plan = EditingPlan(clips=[
        ClipConfig(id='a', image_url='/api/uploads/a.jpg', start_time=0, duration=3, media_type='image'),
        ClipConfig(id='b', image_url='/api/uploads/b.jpg', start_time=3, duration=3, media_type='image'),
    ], duration_seconds=6)
    strategy = TasteEditingStrategy(color_mood='noir', pacing='slow', motion='slow_zoom',
                                    clip_motion='static', transition_preferences=['dip_black'],
                                    color_strength=0.9, beat_sync=False)
    out = apply_strategy_to_plan(plan, strategy)
    assert out.style == 'noir' and out.cut_pacing == 'slow' and out.beat_sync is False
    assert out.clips[0].motion == 'static' and out.clips[0].transition == 'dip_black'
    assert out.transitions and out.transitions[0].type == 'dip_black'


def test_base_template_selection():
    assert base_template_for(TasteEditingStrategy(pacing='fast')) == 'fitness_energy'
    assert base_template_for(TasteEditingStrategy(color_mood='minimal')) == 'minimalist'
    assert base_template_for(TasteEditingStrategy(color_mood='cinematic')) == 'cinematic'
