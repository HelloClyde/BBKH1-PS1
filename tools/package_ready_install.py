"""Add the publisher-authorized BIOS to an existing verified release install ZIP."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-install', type=Path, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    parser.add_argument('--bios', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'dist/ready')
    args = parser.parse_args()
    version = (ROOT/'VERSION').read_text().strip()
    permission = json.loads((ROOT/'docs/evidence/bios-redistribution.json').read_text(encoding='utf-8'))
    assert permission['redistribution_basis']['confirmed']
    bios = args.bios.read_bytes()
    assert len(bios) == permission['bytes'] and digest(bios) == permission['sha256'], 'Unexpected BIOS'
    checksums = dict(reversed(line.split('  ', 1)) for line in args.checksums.read_text(encoding='ascii').splitlines())
    assert digest(args.base_install.read_bytes()) == checksums[args.base_install.name], 'Base ZIP checksum mismatch'
    with zipfile.ZipFile(args.base_install) as source:
        assert source.testzip() is None
        assert len(source.namelist()) == len(set(source.namelist()))
        entries = {item.filename: source.read(item) for item in source.infolist() if not item.is_dir()}
    for name in entries:
        path = PurePosixPath(name)
        assert not path.is_absolute() and '..' not in path.parts and ':' not in name and '\\' not in name
        assert path.suffix.lower() not in {'.mcd', '.sav', '.cue', '.iso'}
    assert permission['file'] not in entries
    bda = entries['应用/程序/PSX.bda']
    metadata = json.loads(entries['PSX.build.json'])
    identity = json.loads((ROOT/f'docs/evidence/release-v{version}.json').read_text(encoding='utf-8'))
    assert metadata['version'] == version
    assert digest(bda) == metadata['sha256'] == identity['bda_sha256']
    preserved = {name: digest(data) for name, data in entries.items() if name not in {'README.md', 'NOTICE.md'}}
    entries[permission['file']] = bios
    entries['README.md'] = (ROOT/'docs/install-ready.md').read_bytes()
    entries['NOTICE.md'] = (ROOT/'NOTICE.md').read_bytes()
    entries['BIOS-ORIGIN.json'] = (json.dumps(permission, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    entries['docs/evidence/bios-redistribution.json'] = entries['BIOS-ORIGIN.json']
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f'BBKH1-PS1-v{version}-ready'
    package = args.output/f'{stem}-install.zip'
    assert not package.exists(), 'Use an empty output directory to preserve earlier package bytes'
    with zipfile.ZipFile(package, 'w') as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert digest(archive.read(permission['file'])) == permission['sha256']
        for name, sha in preserved.items():
            assert digest(archive.read(name)) == sha, name
    manifest = {
        'version': version, 'package': package.name, 'package_sha256': digest(package.read_bytes()),
        'packaging_source_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'package_bytes': package.stat().st_size, 'base_install': args.base_install.name,
        'base_install_sha256': checksums[args.base_install.name], 'bda_sha256': digest(bda),
        'bios': permission, 'base_payloads_preserved': True, 'zip_integrity': True,
        'bda_bytes_changed': False, 'new_hardware_test': False,
        'scope': f'Packaging-only addition to v{version}; reuse the published exact BDA and existing validation evidence'
    }
    record = args.output/f'{stem}-install.json'
    record.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.output/f'{stem}-SHA256SUMS.txt').write_text(
        ''.join(digest(path.read_bytes())+'  '+path.name+'\n' for path in (package, record)), encoding='ascii')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
