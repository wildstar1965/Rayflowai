"""Caption Engine adaptation: deterministic contracts, exports and font shaping."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, features

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.main import app
from app.schemas.captions import CaptionDocument, EngineTranscript
from app.schemas.editing_plan import SubtitleSegment, SubtitleStyle, WordTiming
from app.services.caption_engine import cue_windows, readable_segments
from app.services.caption_documents import export_document, import_engine_transcript
from app.services import caption_frames, caption_fonts, speech_transcription as speech

client = TestClient(app)


def words(tokens, step=.3):
    return [dict(word=word, start=index*step, end=index*step+.2) for index, word in enumerate(tokens)]


def document(text='Hello world.', timed=True, end=2):
    return CaptionDocument(duration_seconds=4, subtitles=[SubtitleSegment(
        id='s', text=text, start_time=0, end_time=end,
        words=[WordTiming(**w) for w in words(text.split())] if timed else [],
        style=SubtitleStyle(caption_mode='phrase', highlight_active=True),
    )])


def test_pause_sentence_danda_and_word_limits():
    style = SubtitleStyle(caption_mode='phrase', max_words=3)
    ws = words(['one', 'two', 'three', 'four।', 'five', 'six'])
    ws[-1].update(start=3, end=3.2)
    cues = list(cue_windows(ws, style, 0, 4))
    assert [[w['word'] for w in group] for _, _, group in cues] == [['one','two','three'],['four।'],['five'],['six']]
    assert all(a[1] <= b[0] for a, b in zip(cues, cues[1:]))
    assert cues[-1][:2] == (3, 3.4)


def test_short_cues_stop_before_next_word_and_document_end():
    ws = [dict(word='Yes!', start=.1,end=.11), dict(word='No!',start=.2,end=.21)]
    assert [c[:2] for c in cue_windows(ws, SubtitleStyle(caption_mode='phrase'),0,.25)] == [(.1,.2),(.2,.25)]


def test_segmentation_preserves_every_word_and_real_timestamps():
    doc = document('one two three four five six seven eight nine', end=3.5)
    grouped = readable_segments(doc.subtitles)
    assert len(grouped) == 3
    assert [w.model_dump() for s in grouped for w in s.words] == [w.model_dump() for w in doc.subtitles[0].words]
    corrected = doc.subtitles[0].model_copy(update={'text':'A corrected sentence'})
    assert readable_segments([corrected])[0].text == 'A corrected sentence'


@pytest.mark.parametrize('fmt', ['srt','vtt','ass','json'])
def test_exports_round_trip_and_do_not_repeat_highlight_frames(fmt):
    doc = document()
    response = client.post(f'/api/captions/export/{fmt}', json=doc.model_dump())
    assert response.status_code == 200
    assert f'rayflow-captions.{fmt}' in response.headers['content-disposition']
    if fmt == 'json':
        assert CaptionDocument.model_validate(response.json()) == doc
    elif fmt == 'ass':
        assert '[Events]' in response.text and '\\c&H0000D4FF&' in response.text
    else:
        assert response.text.count('Hello world.') == 1
        assert ' --> ' in response.text
        assert ('WEBVTT' in response.text) == (fmt == 'vtt')


def test_utf8_escape_and_timestamp_carry():
    doc = document('विद्या & <b>ಕನ್ನಡ</b>\nnext', timed=False)
    doc.duration_seconds = 3602
    doc.subtitles[0].start_time = 3599.9996
    doc.subtitles[0].end_time = 3601.25
    output = export_document(doc, 'vtt')
    assert '01:00:00.000 --> 01:00:01.250' in output
    assert 'विद्या &amp; &lt;b&gt;ಕನ್ನಡ&lt;/b&gt;\nnext' in output
    # ASS may insert valid color/size overrides between a line break and text.
    ass_text = re.sub(r'\{[^}]*\}', '', export_document(doc, 'ass'))
    assert '\\Nnext' in ass_text


@pytest.mark.parametrize('mutation', ['overlap','outside','empty','word_order','duplicate','injection'])
def test_invalid_edits_are_rejected(mutation):
    data = document().model_dump()
    sub = data['subtitles'][0]
    if mutation == 'overlap': data['subtitles'].append({**sub,'id':'other','start_time':1})
    elif mutation == 'outside': sub['end_time'] = 5
    elif mutation == 'empty': sub['text'] = ' '
    elif mutation == 'word_order': sub['words'][1]['start'] = .05
    elif mutation == 'duplicate': data['subtitles'].append({**sub,'start_time':2,'end_time':4,'words':[]})
    elif mutation == 'injection': sub['words'][0]['color'] = 'bad\n00'
    assert client.post('/api/captions/validate', json=data).status_code == 422


def engine_transcript():
    return EngineTranscript(duration=3, hasWordTimings=True, language='hi', words=[
        dict(text='आज',roman='aaj',start=0,end=.3,speakerId='speaker_1',confidence=.9),
        dict(text='meeting',start=.4,end=.7,speakerId='speaker_1'),
        dict(text='um',start=.8,end=.9,keep=False),
        dict(text='[laugh]',start=1,end=1.2,type='audio_event'),
        dict(text='है।',roman='hai.',start=1.4,end=1.7,speakerId='speaker_2'),
    ])


def test_engine_import_keeps_speakers_and_omits_removed_non_speech():
    captions = import_engine_transcript(engine_transcript(), 'source.wav', True)
    assert [s.text for s in captions] == ['aaj meeting','hai.']
    assert captions[0].words[0].speaker_id == 'speaker_1'
    assert captions[0].words[0].confidence == .9
    assert captions[0].words[0].start == 0


def test_engine_import_refuses_guessed_timings_and_overlap():
    transcript = engine_transcript()
    transcript.hasWordTimings = False
    with pytest.raises(ValueError,match='genuine'): import_engine_transcript(transcript,'a.wav')
    transcript.hasWordTimings = True
    transcript.words[1].start = .1
    with pytest.raises(ValueError,match='ordered'): import_engine_transcript(transcript,'a.wav')


@pytest.mark.parametrize('filename', ['../a.wav','C:\\a.wav','/tmp/a.wav','%2e%2e%2fa.wav','https://host/a.wav','image.png'])
def test_transcription_rejects_paths_and_unsupported_media(filename):
    assert client.post('/api/transcribe',json={'media_filename':filename,'model_size':'tiny'}).status_code == 400


def test_api_import_and_missing_model_language_validation(tmp_path, monkeypatch):
    monkeypatch.setattr(speech,'UPLOAD_DIR',tmp_path)
    (tmp_path/'a.wav').write_bytes(b'audio fixture')
    for options in [{'model_size':'C:/models'}, {'language':'not-a-language'}]:
        assert client.post('/api/transcribe',json={'media_filename':'a.wav',**options}).status_code == 400
    response = client.post('/api/captions/import',json={'media_filename':'a.wav','transcript':engine_transcript().model_dump()})
    assert response.status_code == 200 and len(response.json()['source_fingerprint']) == 64
    assert client.post('/api/transcribe',json={'media_filename':'missing.wav'}).status_code == 404


def test_real_progress_and_metadata_without_fabricated_word_times(monkeypatch):
    model = Mock()
    model.transcribe.return_value = (iter([SimpleNamespace(start=0,end=1,text='Hello',words=[
        SimpleNamespace(word='Hello',start=.2,end=.8,probability=.9)])]), SimpleNamespace(language='en',duration=2))
    monkeypatch.setattr(speech,'_model',lambda *args:model)
    reports = []
    result = speech._transcribe_uncached('unused','tiny',None,report=lambda *args:reports.append(args))
    assert result[0].words[0].start == .2 and result[0].words[0].confidence == .9
    assert reports[-1][0] > reports[-2][0] and reports[-1][2] == 'en'


@pytest.mark.parametrize('text,script', [('विद्या क्षेत्र','Devanagari'),('ಕನ್ನಡ ಪುಸ್ತಕ','Kannada'),('చెప్తాను','Telugu'),('தமிழ்','Tamil'),('বাংলা','Bengali')])
def test_native_script_shaping_and_preview_pixels(tmp_path,monkeypatch,text,script):
    if not features.check_feature('raqm'): pytest.skip('Pillow RAQM is unavailable')
    monkeypatch.setattr(caption_frames,'CACHE_DIR',tmp_path)
    assert caption_fonts.script_for(text) == script
    font = caption_fonts.caption_font(text,42,'Arial',700)
    assert f'NotoSans{script}' in str(font.path)
    segment = document(text,timed=False).subtitles[0]
    segment.style.tracking = 3
    events = caption_frames.caption_events([segment],640,360)
    with Image.open(events[0]['path']) as image:
        assert image.getbbox() and image.size == (640,360)


def test_capabilities_are_honest():
    response = client.get('/api/captions/capabilities')
    assert response.status_code == 200
    assert response.json()['local'] and not response.json()['diarization']
    assert 'hi' in response.json()['languages']
