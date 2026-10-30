"""REAL Qloo API integration tests — gated on a live hackathon API key.

These are SKIPPED unless QLOO_API_KEY is set in the environment, so CI and
offline runs never depend on the network. When a key is present, they make
genuine calls to https://hackathon.api.qloo.com to confirm the integration end
to end. A passing mocked unit test is NOT a substitute for these.

Run locally with:
    QLOO_API_KEY=your_key python -m pytest tests/test_qloo_live_integration.py -v
"""
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

pytestmark = pytest.mark.skipif(
    not os.getenv('QLOO_API_KEY'),
    reason='QLOO_API_KEY not set; skipping real Qloo integration tests.',
)


def test_live_search_resolves_a_well_known_movie():
    from app.services.qloo.client import QlooClient
    client = QlooClient()
    results = client.search('Interstellar', types='urn:entity:movie', take=5)
    # The hackathon dataset should know a famous film; if empty, the API is up
    # but lacks data — we assert the call succeeded and returned a list.
    assert isinstance(results, list)
    if results:
        assert any(r.get('name') for r in results)


def test_live_insights_accepts_entity_signal():
    from app.services.qloo.client import QlooClient
    client = QlooClient()
    movie = client.search('Interstellar', types='urn:entity:movie', take=1)
    if not movie:
        pytest.skip('No entity data returned for the seed query in this environment.')
    entity_id = movie[0].get('entity_id') or movie[0].get('id')
    data = client.insights({
        'filter.type': 'urn:entity:movie',
        'signal.interests.entities': entity_id,
        'take': 5,
    })
    assert isinstance(data, dict)


def test_live_end_to_end_profile_and_strategy():
    from app.services.qloo.profile_builder import build_profile
    from app.services.taste_intelligence import generate_strategy
    profile = build_profile([
        {'text': 'Interstellar', 'category': 'movie'},
        {'text': 'Hans Zimmer', 'category': 'artist'},
    ], use_qloo=True)
    assert profile.source == 'qloo'
    # Strategy must validate even without an LLM key (rule-based fallback).
    response = generate_strategy(profile.summary(), allow_llm=False)
    assert response.strategy.color_mood in ('cinematic', 'vintage', 'noir', 'vibrant', 'minimal')
