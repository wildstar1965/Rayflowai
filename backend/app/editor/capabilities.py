"""Report encoders present in the configured FFmpeg, without guessing GPU readiness."""
from functools import lru_cache
import subprocess


@lru_cache(maxsize=4)
def codec_capabilities(executable):
    catalog = {
        'h264': ('libx264', 'h264_nvenc', 'h264_videotoolbox'),
        'hevc': ('libx265', 'hevc_nvenc', 'hevc_videotoolbox'),
        'prores': ('prores_ks', 'prores', 'prores_videotoolbox'),
    }
    try:
        result = subprocess.run([str(executable), '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=5)
        listed = {parts[1] for line in result.stdout.splitlines() if len(parts := line.split()) > 1 and parts[0].startswith('V')}
        if result.returncode:
            listed = set()
    except (OSError, subprocess.TimeoutExpired):
        listed = set()
    capabilities = {}
    for codec, names in catalog.items():
        software = any(name in listed for name in names if name.startswith('lib') or name in ('prores', 'prores_ks'))
        capabilities[codec] = {'available': software, 'encoders': [name for name in names if name in listed],
            'hardware_requires_validation': any(name in listed for name in names if name.endswith(('_nvenc', '_videotoolbox'))),
            'reason': None if software else 'No software encoder found. Hardware-only encoders need a working device; the operator must validate them.'}
    return capabilities
