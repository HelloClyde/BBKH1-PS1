"""Read the authorized BIOS from the earlier public release, with pinned hashes."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/HelloClyde/BBKH1-PS1/releases/download/v0.1.3/BBKH1-PS1-v0.1.3-ready-install.zip'
ARCHIVE_SHA256='a290928047103abd3073ce510d2872763ec997cfcf19c19ec0df7922f0d03902'


def release_bios():
    record=json.loads((ROOT/'docs/evidence/bios-redistribution.json').read_text(encoding='utf-8'))
    assert record['redistribution_basis']['confirmed']
    cached=ROOT/'build/release-bios/authorized-bios-source.zip'
    if cached.exists():
        archive=cached.read_bytes()
    else:
        request=urllib.request.Request(URL,headers={'User-Agent':'BBKH1-PS1-release-builder'})
        with urllib.request.urlopen(request,timeout=60) as response:
            archive=response.read(2*1024*1024)
        assert hashlib.sha256(archive).hexdigest()==ARCHIVE_SHA256,'BIOS source archive checksum mismatch'
        cached.parent.mkdir(parents=True,exist_ok=True);cached.write_bytes(archive)
    assert hashlib.sha256(archive).hexdigest()==ARCHIVE_SHA256,'Cached BIOS source checksum mismatch'
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        assert source.namelist().count(record['file'])==1
        bios=source.read(record['file'])
    assert len(bios)==record['bytes'] and hashlib.sha256(bios).hexdigest()==record['sha256']
    return bios,{**record,'distribution_source':{'url':URL,'archive_sha256':ARCHIVE_SHA256}}
