"""Verify complete source ZIP snapshots when no Git metadata is available."""
import hashlib,json
from pathlib import Path
def verify(root):
    manifest=json.loads((root/'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    dependencies=json.loads((root/'UPSTREAM.json').read_text(encoding='utf-8'))
    assert manifest['dependencies']==dependencies,'Source dependency identity mismatch'
    for name,expected in manifest['files'].items():
        p=(root/name).resolve()
        assert p.is_relative_to(root.resolve()),'Unsafe manifest path'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,'Source snapshot mismatch: '+name
    return manifest
