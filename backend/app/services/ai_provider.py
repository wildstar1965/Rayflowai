"""Shared, server-only Director transport. Never surface upstream bodies or secrets."""
import json
import os
import re
import requests

from app.services.provider_settings import setting

# Verified in the official model catalogs on 2026-10-24. Account access is tested separately.
MODELS = {'openai': ['gpt-6-astra', 'gpt-4.1'], 'anthropic': ['claude-opus-5-5']}
# Starting choices only; Find models queries the account's current Gemini catalog.
MODELS['gemini'] = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-3-flash-preview', 'gemini-3.1-pro-preview']
LABELS = {'openai': 'OpenAI', 'anthropic': 'Anthropic', 'gemini': 'Google Gemini', 'openrouter': 'OpenRouter', 'agentrouter': 'Agent Router', 'ollama': 'Ollama'}
GEMINI_BASE = 'https://generativelanguage.googleapis.com/v1beta'


def gemini_model(value):
    model = value.strip().removeprefix('models/')
    if not re.fullmatch(r'gemini-[A-Za-z0-9._-]+', model):
        raise ProviderError('Enter a Gemini model ID, or choose one with Find models.')
    return model


def agentrouter_base():
    value = os.getenv('AGENTROUTER_BASE_URL', 'https://agentrouter.org/v1').rstrip('/')
    if value not in ('https://agentrouter.org/v1', 'https://co.agentrouter.org/v1'):
        raise ProviderError('Use the Agent Router HTTPS /v1 endpoint in AGENTROUTER_BASE_URL.')
    return value


class ProviderError(ValueError):
    pass


def selected_provider():
    selected = setting('AI_PROVIDER', 'auto')
    if selected == 'auto':
        selected = next((p for p in LABELS if setting(p.upper() + '_API_KEY')), '')
    if selected not in LABELS:
        raise ProviderError('Connect Gemini, OpenAI, Anthropic, or OpenRouter in Connections to use the conversational Director. Manual editing is available without a key.')
    return selected


def configuration(provider, key=None, model=None):
    key = key.strip() if key else setting(provider.upper() + '_API_KEY').strip()
    model = model or setting(provider.upper() + '_MODEL') or (MODELS.get(provider) or ['gpt-6-astra' if provider == 'agentrouter' else 'openrouter/free'])[0]
    if provider not in LABELS:
        raise ProviderError('Unsupported AI provider.')
    if provider == 'gemini':
        model = gemini_model(model)
    elif provider in MODELS and model not in MODELS[provider]:
        raise ProviderError('Select a supported model in Connections.')
    if not key:
        raise ProviderError(f'Add your {LABELS[provider]} API key in Connections.')
    if len(model) > 200 or any(c.isspace() for c in model):
        raise ProviderError('Enter a model ID without spaces in Connections.')
    if len(key) > 4096 or any(c in key for c in '\r\n\x00'):
        raise ProviderError('Enter a valid single-line API key.')
    return key, model


def _request(provider, method, url, key, **kwargs):
    headers = {'Content-Type': 'application/json'}
    if provider == 'anthropic':
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    elif provider == 'gemini':
        headers['x-goog-api-key'] = key
    else:
        headers['Authorization'] = 'Bearer ' + key
    try:
        response = requests.request(method, url, headers=headers, timeout=(10, 120), allow_redirects=False, **kwargs)
    except requests.Timeout:
        raise ProviderError('The AI provider timed out. Retry your request.') from None
    except requests.RequestException:
        raise ProviderError('The AI provider could not be reached. Check network access and retry.') from None
    status = response.status_code
    if provider == 'gemini' and status in (400, 401, 403):
        # Inspect known Google errors, but never return upstream text or credentials.
        try:
            error = response.json().get('error', {})
            details = error.get('details', [])
            reasons = {item.get('reason') for item in details if isinstance(item, dict)}
            message = str(error.get('message', '')).lower()
        except (ValueError, TypeError, AttributeError):
            reasons, message = set(), ''
        if 'leaked' in message:
            raise ProviderError('Google blocked this key as leaked. Create a replacement in Google AI Studio and save it in Connections.')
        if reasons & {'API_KEY_INVALID', 'API_KEY_EXPIRED'} or 'api key not valid' in message or 'api key expired' in message:
            raise ProviderError('Google rejected this API key. Copy a valid Gemini API key from Google AI Studio into Connections.')
        if reasons & {'API_KEY_SERVICE_BLOCKED', 'API_KEY_HTTP_REFERRER_BLOCKED', 'API_KEY_IP_ADDRESS_BLOCKED', 'SERVICE_DISABLED'}:
            raise ProviderError('Google blocked this key or project from using the Gemini API. Check API restrictions and enable the Generative Language API for backend requests.')
    if status in (401, 403):
        raise ProviderError('Credentials were rejected or model access is forbidden. Check your key in Connections.')
    if status == 429:
        raise ProviderError('The provider rate or usage limit was reached. Check billing or wait before retrying.')
    if status in (400, 404):
        raise ProviderError('The selected model is unavailable for this account or rejected the request. Check Connections.')
    if not 200 <= status < 300:
        raise ProviderError('The AI provider is unavailable. Please try again later.')
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except ValueError:
        raise ProviderError('The AI provider returned an invalid response.') from None


def test_connection(provider, key=None, model=None):
    try:
        key, model = configuration(provider, key, model)
        if provider == 'gemini':
            data = _request(provider, 'GET', f'{GEMINI_BASE}/models/{model}', key)
            if data.get('name') != 'models/' + model or 'generateContent' not in data.get('supportedGenerationMethods', []):
                raise ProviderError('Google did not confirm text generation for the selected model. Use Find models in Connections.')
            return {'ok': True, 'verified': True, 'message': 'Gemini key and selected model verified. Generation remains subject to quota and billing.'}
        if provider == 'agentrouter':
            data = _request(provider, 'POST', agentrouter_base() + '/chat/completions', key, json={
                'model': model, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}], 'max_tokens': 32,
            })
            if not data.get('choices'):
                raise ProviderError('Agent Router returned no model response.')
            return {'ok': True, 'verified': True, 'message': 'Agent Router accepted a short generation request for the selected model.'}
        host = 'api.openai.com' if provider == 'openai' else 'api.anthropic.com'
        data = _request(provider, 'GET', f'https://{host}/v1/models/{model}', key)
        if data.get('id') != model:
            raise ProviderError('The provider did not confirm the selected model.')
        return {'ok': True, 'verified': True, 'message': 'Key and model access verified. Generation remains subject to account limits.'}
    except ProviderError as exc:
        return {'ok': False, 'verified': False, 'message': str(exc)}


def gemini_models():
    key = setting('GEMINI_API_KEY').strip()
    if not key:
        raise ProviderError('Save your Google Gemini key in Connections before finding models.')
    models, page, seen = [], '', set()
    for _ in range(20):
        data = _request('gemini', 'GET', GEMINI_BASE + '/models', key,
                        params={'pageSize': 1000, **({'pageToken': page} if page else {})})
        for item in data.get('models', []):
            name = item.get('name', '').removeprefix('models/')
            if ('generateContent' in item.get('supportedGenerationMethods', []) and name.startswith('gemini-')
                    and not re.search(r'image|tts|live|audio|robotics|computer-use', name)):
                models.append(gemini_model(name))
        page = data.get('nextPageToken', '')
        if not page:
            return list(dict.fromkeys(models))
        if page in seen:
            break
        seen.add(page)
    raise ProviderError('Google model discovery did not finish. Retry Find models.')


def generate_plan(messages):
    provider = selected_provider()
    if provider == 'ollama':
        from app.services.ollama_client import generate_ollama, OllamaError
        prompt = '\n\n'.join(message['content'] for message in messages)
        if len(prompt) > 22000:
            raise ProviderError('This project exceeds the local Director context. Use a hosted provider or a shorter sequence.')
        try:
            content = generate_ollama(prompt, max_tokens=1024, context_size=8192)
            return json.loads(content)
        except OllamaError as exc:
            raise ProviderError(str(exc)) from None
        except (ValueError, TypeError):
            raise ProviderError('Ollama returned a malformed editing plan. No changes were made.') from None
    key, model = configuration(provider)
    if provider == 'gemini':
        data = _request(provider, 'POST', f'{GEMINI_BASE}/models/{model}:generateContent', key, json={
            'systemInstruction': {'parts': [{'text': '\n\n'.join(m['content'] for m in messages if m['role'] == 'system')}]},
            'contents': [{'role': 'model' if m['role'] == 'assistant' else 'user', 'parts': [{'text': m['content']}]}
                         for m in messages if m['role'] != 'system'],
            'generationConfig': {'responseMimeType': 'application/json', 'maxOutputTokens': 8192},
        })
        try:
            candidate = data['candidates'][0]
            if candidate.get('finishReason') != 'STOP':
                raise ProviderError('Gemini did not finish an editing plan. Try a smaller request.')
            content = ''.join(part.get('text', '') for part in candidate['content']['parts'] if not part.get('thought'))
        except (KeyError, IndexError, TypeError):
            raise ProviderError('Gemini returned no editing plan. Try rephrasing your request.') from None
    elif provider == 'anthropic':
        data = _request(provider, 'POST', 'https://api.anthropic.com/v1/messages', key, json={
            'model': model, 'max_tokens': 8192, 'system': messages[0]['content'], 'messages': messages[1:],
        })
        if data.get('stop_reason') != 'end_turn':
            raise ProviderError('The provider did not finish an editing plan. Try a smaller request.')
        content = ''.join(part.get('text', '') for part in data.get('content', []) if part.get('type') == 'text')
    else:
        url = (agentrouter_base() + '/chat/completions' if provider == 'agentrouter' else
               'https://api.openai.com/v1/chat/completions' if provider == 'openai' else 'https://openrouter.ai/api/v1/chat/completions')
        data = _request(provider, 'POST', url, key, json={
            'model': model, 'messages': messages, 'max_completion_tokens': 8192,
            'response_format': {'type': 'json_object'},
        })
        try:
            choice = data['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise ProviderError('The provider did not finish an editing plan. Try a smaller request.')
            content = choice['message']['content']
        except (KeyError, IndexError, TypeError):
            raise ProviderError('The provider returned no editing plan.') from None
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        raise ProviderError('The provider returned a malformed editing plan. No changes were made.') from None
