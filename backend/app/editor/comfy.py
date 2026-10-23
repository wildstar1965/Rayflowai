"""Namespace ComfyUI inputs and authorize history/output access per guest."""
import copy
import hashlib
import json
import os
import uuid
from urllib.parse import parse_qs, unquote

from .context import owner
from .store import store, safe_relative

NODES = {'CheckpointLoaderSimple', 'LoraLoader', 'CLIPLoader', 'CLIPTextEncode', 'VAELoader',
         'LoadImage', 'VAEEncode', 'EmptyLatentImage', 'KSampler', 'VAEDecode', 'SaveImage',
         'FreeFuseLoRALoader', 'FreeFuseConceptMap', 'FreeFuseTokenPositions',
         'FreeFusePhase1Sampler', 'FreeFuseMaskApplicator'}


def file_id(filename, subfolder='', kind='output'):
    return hashlib.sha256(json.dumps([filename, subfolder, kind]).encode()).hexdigest()


def prepare(path, query, method, body, form):
    path = unquote(path)
    if method == 'GET' and path in ('/system_stats', '/object_info'):
        return body, form
    if method == 'GET' and path.startswith('/history/'):
        prompt = path.removeprefix('/history/')
        if not store.get('comfy_prompts', prompt, owner()):
            raise ValueError('ComfyUI prompt does not belong to this workspace.')
        return body, form
    if method == 'GET' and path == '/view':
        params = parse_qs(query)
        identity = file_id(params.get('filename', [''])[0], params.get('subfolder', [''])[0], params.get('type', ['output'])[0])
        if not store.get('comfy_files', identity, owner()):
            raise ValueError('ComfyUI output does not belong to this workspace.')
        return body, form
    if method == 'POST' and path == '/upload/image':
        images = [copy.deepcopy(entry) for entry in form or [] if entry.get('name') == 'image' and entry.get('base64')]
        if len(images) != 1:
            raise ValueError('Upload one reference image.')
        extension = '.' + images[0].get('filename', 'input.png').rsplit('.', 1)[-1].lower()
        if extension not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Use PNG, JPEG or WebP reference images.')
        images[0]['filename'] = uuid.uuid4().hex + extension
        return None, images + [{'name': 'subfolder', 'value': 'rayflow/' + owner()}, {'name': 'type', 'value': 'input'}]
    if method == 'POST' and path == '/prompt':
        data = json.loads(body or '{}')
        workflow = data.get('prompt', {})
        if not isinstance(workflow, dict) or not 1 <= len(workflow) <= 300:
            raise ValueError('A ComfyUI workflow must contain 1 to 300 nodes.')
        allowed = NODES | set(filter(None, os.getenv('EDITOR_COMFYUI_EXTRA_NODES', '').split(',')))
        for node in workflow.values():
            if not isinstance(node, dict) or node.get('class_type') not in allowed:
                raise ValueError('This ComfyUI node requires backend operator approval.')
            inputs = node.get('inputs', {})
            for key, value in inputs.items():
                if key in ('ckpt_name', 'lora_name', 'clip_name', 'vae_name') and isinstance(value, str):
                    safe_relative(value)
            if node['class_type'] == 'SaveImage':
                inputs['filename_prefix'] = 'rayflow/' + owner() + '/' + uuid.uuid4().hex
            if node['class_type'] == 'LoadImage':
                reference = inputs.get('image', '')
                if not isinstance(reference, str) or not store.get('comfy_inputs', hashlib.sha256(reference.encode()).hexdigest(), owner()):
                    raise ValueError('Upload this ComfyUI reference image in your workspace first.')
        return json.dumps({'prompt': workflow, 'client_id': owner()}), None
    raise ValueError('This ComfyUI operation requires backend operator access. Global queues and interrupts are not available to guests.')


def record(path, method, result):
    if not 200 <= result.get('status', 500) < 300 or 'text' not in result:
        return
    data = json.loads(result['text'])
    if method == 'POST' and path == '/prompt' and data.get('prompt_id'):
        store.put('comfy_prompts', data['prompt_id'], owner(), {})
    if method == 'POST' and path == '/upload/image' and data.get('name'):
        reference = safe_relative('/'.join(filter(None, [data.get('subfolder'), data['name']])))
        store.put('comfy_inputs', hashlib.sha256(reference.encode()).hexdigest(), owner(), {'reference': reference})
    if method == 'GET' and path.startswith('/history/'):
        prompt = path.removeprefix('/history/')
        # ComfyUI must not return other prompt records even if its server ignores the path.
        data = {prompt: data[prompt]} if prompt in data else {}
        result['text'] = json.dumps(data)
        for output in data.get(prompt, {}).get('outputs', {}).values():
            for media in output.get('images', []):
                filename = safe_relative(media['filename'])
                subfolder = media.get('subfolder', '')
                if subfolder:
                    safe_relative(subfolder)
                store.put('comfy_files', file_id(filename, subfolder, media.get('type', 'output')), owner(), {})
