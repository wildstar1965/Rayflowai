"""Operator-configured NotebookLM MCP over HTTP, with per-workspace authorization."""
import json
import os
import uuid
import requests
from .context import owner
from .providers import credential, validate_url
from .security import encrypt, decrypt
from .store import store

METHODS = {'initialize', 'tools/list', 'resources/list', 'resources/read', 'tools/call'}
NOTEBOOK_TOOLS = {'notebook_list', 'list_notebooks', 'notebooks_list', 'notebook_query', 'query_notebook', 'notebooks_query'}


def call(method, params=None):
    target = os.getenv('EDITOR_NOTEBOOKLM_URL', '')
    if not target:
        raise ValueError('The backend operator must configure a NotebookLM MCP HTTP endpoint.')
    if method not in METHODS:
        raise ValueError('Unsupported NotebookLM MCP operation.')
    if method == 'tools/call' and (params or {}).get('name') not in NOTEBOOK_TOOLS:
        raise ValueError('This hosted connection permits NotebookLM listing and queries only.')
    key = credential('notebooklm')
    if not key:
        raise ValueError('Add your NotebookLM MCP token in Connections. Each judge must use their own authorization.')
    validate_url(target, local=True)
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
               'MCP-Protocol-Version': '2025-03-26'}
    session = store.get('mcp_sessions', owner(), owner())
    if session and method != 'initialize':
        headers['Mcp-Session-Id'] = decrypt(session['encrypted'], owner(), 'mcp')
    if method == 'initialize':
        params = {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'Rayflow', 'version': '1.0'}}
    response = requests.post(target, headers=headers, json={'jsonrpc': '2.0', 'id': str(uuid.uuid4()), 'method': method, 'params': params or {}},
                             timeout=(10, 120), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError('NotebookLM MCP rejected the request. Check the endpoint and your authorization.')
    session_id = response.headers.get('mcp-session-id')
    if session_id:
        store.put('mcp_sessions', owner(), owner(), {'encrypted': encrypt(session_id, owner(), 'mcp')})
    if 'text/event-stream' in response.headers.get('content-type', ''):
        values = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:') and line[5:].strip()]
        value = next((value for value in reversed(values) if 'result' in value or 'error' in value), {})
    else:
        value = response.json()
    if value.get('error'):
        raise ValueError('NotebookLM MCP could not complete this operation.')
    if method == 'initialize':
        if session_id:
            headers['Mcp-Session-Id'] = session_id
        notification = requests.post(target, headers=headers, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'}, timeout=(10, 20), allow_redirects=False)
        if notification.status_code >= 300:
            raise ValueError('NotebookLM MCP initialization was not accepted.')
        return {'ok': True}
    result = value.get('result', {})
    return json.loads(json.dumps(result).replace(key, '[redacted]'))
