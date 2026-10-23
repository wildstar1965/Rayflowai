"""Contracts for the reference renderer and honest model availability."""
import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.schemas.editing_plan import SubtitleStyle, SubtitleSegment, WordTiming
from app.services.caption_frames import caption_units
from app.services.caption_engine import readable_segments
from app.services.caption_fonts import script_runs
from app.services.caption_layout import layout_words, paint_caption
from app.services import speech_models as models


def words():
    return [{'word': 'ALPHA', 'start': 0, 'end': .3, 'emphasis': True, 'size_multiplier': 1.25},
            {'word': 'gypsy', 'start': .5, 'end': .8}, {'word': 'iii', 'start': .9, 'end': 1.2}]


def test_baseline_and_uniform_resting_size_ignore_legacy_heuristics():
    items, bounds, size, stroke = layout_words(words(), SubtitleStyle(), 1080, 1920)
    assert len({item['baseline'] for item in items}) == 1
    assert {run['font'].size for item in items for run in item['resting']} == {72}
    assert all(item['slot'] >= max(item['base_width'], item['active_width']) for item in items)
    assert all(0 < left < right < 1080 and 0 < top < bottom < 1920 for left,top,right,bottom in bounds)


def test_color_only_highlighting_never_moves_glyphs_or_backdrop():
    style = SubtitleStyle(active_scale=1, background_opacity=.6)
    images = [np.asarray(paint_caption(words(), style, 1080, 1920, index)) for index in range(3)]
    assert all(np.array_equal(images[0][:,:,3], image[:,:,3]) for image in images[1:])
    assert not np.array_equal(images[0], images[1])


def test_active_scaling_leaves_unaffected_word_pixels_fixed():
    style = SubtitleStyle(active_scale=1.08)
    items, _, _, _ = layout_words(words(), style, 1080, 1920)
    untouched = items[2]
    x, baseline = round(untouched['x']), round(untouched['baseline'])
    a = np.asarray(paint_caption(words(), style, 1080, 1920, 0))
    b = np.asarray(paint_caption(words(), style, 1080, 1920, 1))
    assert np.array_equal(a[baseline-100:baseline+30,x:x+round(untouched['slot'])],
                          b[baseline-100:baseline+30,x:x+round(untouched['slot'])])


def test_reference_scaling_and_unicode_runs():
    _, _, full, outline = layout_words(words(), SubtitleStyle(), 1080, 1920)
    _, _, half, half_outline = layout_words(words(), SubtitleStyle(), 540, 960)
    assert full == 2*half and outline == 2*half_outline
    assert script_runs('Helloविद्या!') == ['Hello', 'विद्या', '!']
    items, _, _, _ = layout_words([{'word':'Helloविद्या'}], SubtitleStyle(), 1080, 1920)
    assert len(items[0]['resting']) == 2
    assert 'NotoSansDevanagari' in str(items[0]['resting'][1]['font'].path)


def test_display_windows_bridge_gaps_without_changing_word_times():
    sub = SubtitleSegment(id='s', text='ALPHA gypsy iii', start_time=0, end_time=1.4,
                          words=[WordTiming(**word) for word in words()], style=SubtitleStyle())
    before = [word.model_dump() for word in sub.words]
    units = caption_units(sub, sub.end_time)
    assert [(a,b,active) for a,b,_,active in units] == [(0,.5,0),(.5,.9,1),(.9,1.2,2)]
    assert [word.model_dump() for word in sub.words] == before


def test_joined_subwords_never_become_an_isolated_caption():
    sub = SubtitleSegment(id='s', text='B-tech.', start_time=0, end_time=1,
        words=[WordTiming(word='B',start=0,end=.3),WordTiming(word='-tech.',start=.3,end=.8)],
        style=SubtitleStyle(max_words=1))
    assert all(len(group)==2 for _,_,group,_ in caption_units(sub, 1))
    assert readable_segments([sub])[0].text == 'B-tech.'


def test_model_catalog_requires_inference_verification(monkeypatch):
    monkeypatch.setattr(models, 'cached_model_path', lambda name: Path('.') if name=='medium' else None)
    monkeypatch.setattr(models, '_VERIFIED', {})
    monkeypatch.setattr(models, '_CHECKING', False)
    assert models.model_catalog()['default_model'] is None
    assert models.model_catalog()['models'][0]['status'] == 'unverified'
    models._VERIFIED['medium'] = {'status':'ready','message':'Verified','runtime':{'device':'cpu','compute_type':'int8'}}
    catalog = models.model_catalog()
    assert catalog['default_model'] == 'medium'
    assert {row['id'] for row in catalog['models']} == {'medium','small','large-v3','turbo'}
    assert all(row['status']=='missing' for row in catalog['models'][1:])


def test_gpu_loading_failure_falls_back_to_same_model_and_reports_it(monkeypatch):
    import faster_whisper
    models.load_model.cache_clear()
    monkeypatch.setattr(models, 'runtime_options', lambda: ('cuda','float16'))
    monkeypatch.setattr(models, '_RUNTIME', {})
    monkeypatch.setattr(models, '_CPU_FALLBACK', set())
    factory = Mock(side_effect=[RuntimeError('missing GPU library in private directory'), Mock()])
    monkeypatch.setattr(faster_whisper, 'WhisperModel', factory)
    try:
        models.load_model('medium')
        assert [call.args[0] for call in factory.call_args_list] == ['medium','medium']
        assert factory.call_args.kwargs['device']=='cpu'
        assert all(call.kwargs['local_files_only'] for call in factory.call_args_list)
        assert 'same model' in models.runtime_for('medium')['notice']
        assert 'private' not in models.runtime_for('medium')['notice']
    finally:
        models.load_model.cache_clear()


def test_insufficient_memory_error_is_actionable_and_redacted():
    error = models.loading_error('medium', RuntimeError('out of memory: private-path'))
    assert 'Small' in str(error) and 'private-path' not in str(error)
