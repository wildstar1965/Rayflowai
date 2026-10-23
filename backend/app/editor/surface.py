"""CPU equivalent of the upstream depth-gradient normal-map processor."""
import base64
import io
import numpy as np
from PIL import Image
from .results import persist_binary
from .context import owner


def depth_gradient(payload, identity):
    source = payload.get('source', {})
    data = str(source.get('base64', '')).split(',')[-1]
    image = Image.open(io.BytesIO(base64.b64decode(data, validate=True)))
    if image.width * image.height > 16_777_216:
        raise ValueError('Depth guides must contain at most 16 megapixels.')
    pixels = np.asarray(image.convert('RGB'), dtype=np.float32) / 255
    luma = pixels @ np.array([.2126, .7152, .0722], dtype=np.float32)
    strength = max(.1, min(8, float(payload.get('options', {}).get('normalStrength', 2))))
    padded = np.pad(luma, ((1, 1), (1, 1)), mode='edge')
    dx = (padded[1:-1, 2:] - padded[1:-1, :-2]) * strength
    dy = (padded[2:, 1:-1] - padded[:-2, 1:-1]) * strength
    normal = np.stack((-dx, -dy, np.ones_like(dx)), axis=2)
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    result = Image.fromarray(np.floor((normal * .5 + .5) * 255 + .5).astype(np.uint8))
    output = io.BytesIO(); result.save(output, format='PNG')
    _, url = persist_binary(owner(), identity, output.getvalue(), 'image/png')
    return {'ok': True, 'url': url, 'outputPath': url, 'outputFolder': '', 'outputName': 'normal-map.png',
            'kind': 'normal', 'engine': 'depth-gradient', 'mediaType': 'image'}
