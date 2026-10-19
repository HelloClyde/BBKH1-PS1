"""Package exact checked release bytes, complete pinned source and checksums."""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path,PurePosixPath
from release_config import ROOT,BUILD

def digest(data):return hashlib.sha256(data).hexdigest()
def read_json(path):return json.loads(path.read_text(encoding='utf-8'))
def git(repo,*args):return subprocess.check_output(['git','-c','safe.directory='+repo.as_posix(),'-C',str(repo),*args])
def safe(name):return name and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name and ':' not in name
def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def public_report(value):
    if isinstance(value,dict):return {k:public_report(v) for k,v in value.items()}
    if isinstance(value,list):return [public_report(v) for v in value]
    if isinstance(value,str) and value.startswith(str(ROOT)):return str(Path(value).relative_to(ROOT)).replace('\\','/')
    return value
def add(z,name,data):
    assert safe(name),name
    info=zipfile.ZipInfo(name,(2026,10,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
    z.writestr(info,data)

def source(destination,dependencies):
    assert Path(git(ROOT,'rev-parse','--show-toplevel').decode().strip()).resolve()==ROOT
    assert not git(ROOT,'status','--porcelain').strip(),'Commit all release sources first'
    commit=git(ROOT,'rev-parse','HEAD').decode().strip();files={}
    for relative,expected in [('',commit)]+[(v.get('path','third_party/'+k),v['commit']) for k,v in dependencies.items()]:
        repo=ROOT/relative
        assert git(repo,'rev-parse','HEAD').decode().strip()==expected
        assert not git(repo,'status','--porcelain','--untracked-files=no').strip()
        if relative:assert git(ROOT,'rev-parse','HEAD:'+relative).decode().strip()==expected
        # git archive exports exactly tracked source; no credentials or local build output.
        import io
        with zipfile.ZipFile(io.BytesIO(git(repo,'archive','--format=zip','HEAD'))) as archive:
            for item in archive.infolist():
                if item.is_dir():continue
                name=(relative+'/' if relative else '')+item.filename
                assert safe(name)
                assert not any(p in {'.git','.tools','__pycache__','node_modules'} for p in PurePosixPath(name).parts)
                assert PurePosixPath(name).suffix.lower() not in {'.bin','.iso','.cue','.rom','.mcd','.sav','.bda','.elf','.exe','.dll','.img','.zip','.7z','.pyc','.o'},name
                assert name not in files;files[name]=archive.read(item)
    manifest={'application_commit':commit,'dependencies':dependencies,'files':{n:digest(d) for n,d in sorted(files.items())}}
    prefix='BBKH1-PS1-v'+(ROOT/'VERSION').read_text().strip()+'/'
    with zipfile.ZipFile(destination,'w') as z:
        for name,data in sorted(files.items()):add(z,prefix+name,data)
        add(z,prefix+'SOURCE-MANIFEST.json',(json.dumps(manifest,indent=2)+'\n').encode())
    return manifest

def verify(output,tag=None,commit=None):
    r=read_json(output/'release-manifest.json');v=(ROOT/'VERSION').read_text().strip()
    assert r['version']==v
    if tag:assert tag=='v'+v
    if commit:assert r['application_commit']==commit
    assert r['exact_bda_hardware_tested'] is False and r['full_firmware_in_ci'] is False
    identity=read_json(ROOT/f'docs/evidence/release-v{v}.json')
    assert identity['version']==v and identity['bda_sha256']==r['bda_sha256'],'Unexpected release bytes; review version evidence before changing'
    assert identity['hardware_tested'] is False and identity['full_firmware_tested'] is False
    entries={}
    for row in (output/'SHA256SUMS.txt').read_text(encoding='ascii').splitlines():
        sha,name=row.split('  ',1);assert safe(name) and '/' not in name and name not in entries
        assert digest((output/name).read_bytes())==sha,name;entries[name]=sha
    expected={'PSX.bda','PSX.build.json','RELEASE-NOTES.md','release-manifest.json',f'BBKH1-PS1-v{v}-install.zip',f'BBKH1-PS1-v{v}-source.zip'}
    assert set(entries)==expected and {p.name for p in output.iterdir()}==expected|{'SHA256SUMS.txt'}
    assert entries['PSX.bda']==r['bda_sha256']
    for name in expected:
        if not name.endswith('.zip'):continue
        with zipfile.ZipFile(output/name) as z:
            assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
            assert all(safe(n) for n in z.namelist())
            if name.endswith('-install.zip'):assert digest(z.read('应用/程序/PSX.bda'))==r['bda_sha256']
            else:
                prefix=f'BBKH1-PS1-v{v}/';m=json.loads(z.read(prefix+'SOURCE-MANIFEST.json'))
                assert m['application_commit']==r['application_commit'] and m['dependencies']==r['dependencies']
                assert set(z.namelist())=={prefix+n for n in m['files']}|{prefix+'SOURCE-MANIFEST.json'}
                for n,sha in m['files'].items():assert digest(z.read(prefix+n))==sha,n
    print('PASS release identity, complete source, install layout and SHA256SUMS.txt')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--verify',action='store_true');ap.add_argument('--tag');ap.add_argument('--commit');ap.add_argument('--output',type=Path,default=ROOT/'dist/release');a=ap.parse_args()
    if a.verify:verify(a.output,a.tag,a.commit);return
    v=(ROOT/'VERSION').read_text().strip()
    if a.tag:assert a.tag=='v'+v
    metadata=read_json(BUILD/'PSX.build.json');bda=(BUILD/'PSX.bda').read_bytes()
    assert digest(bda)==metadata['sha256'] and metadata['version']==v
    assert metadata['application_title']=='PSX' and metadata['file_name']=='PSX.bda'
    assert metadata['icon_sha256']==digest((ROOT/'assets/icon.png').read_bytes())
    assert not metadata['options']['test_frames'] and not metadata['options']['benchmark'] and not metadata['options']['profile']
    assert metadata['options']['cpu_mhz']==408 and metadata['options']['audio_turbo']
    for name,sha in metadata['source_sha256'].items():assert digest((ROOT/name).read_bytes())==sha,'Rebuild after source changes: '+name
    sys.path.insert(0,str(ROOT/'sdk'));from h1_bda.validate import validate_bda
    envelope=validate_bda(BUILD/'PSX.bda');assert envelope['ok'] and envelope['title']=='PSX' and envelope['category']==0x47
    reports={}
    for path in [ROOT/'build/verification/smoke/smoke.json',ROOT/'build/verification/runtime.json',ROOT/'build/model/hud-408/result.json',BUILD/'turbo-frontend.json',BUILD/'frontend.json',BUILD/'spu-samples-equivalence.json',BUILD/'present-equivalence.json',ROOT/'build/verification/pause-menu/result.json',ROOT/'build/verification/settings.json']:
        report=read_json(path);assert report['ok'] and report.get('sha256',report.get('bda_sha256'))==metadata['sha256'];reports[path.relative_to(ROOT).as_posix()]=public_report(report)
    contracts=ROOT/'build/jit-test6-bench-idle'
    contract_meta=read_json(contracts/'PSX.build.json')
    for name in ['idle-equivalence.json','disc-contract.json','lifecycle.json']:
        report=read_json(contracts/name);assert report['ok'] and report['sha256']==contract_meta['sha256'];reports[name]=public_report(report)
    mapping=read_json(ROOT/'build/verification/mapping.json');assert mapping['ok'] and mapping['sha256']==contract_meta['sha256'];reports['mapping.json']=mapping
    clock=read_json(ROOT/'build/clock-control-model/model.json');assert clock['ok']
    a.output.mkdir(parents=True,exist_ok=True)
    manifest=source(a.output/f'BBKH1-PS1-v{v}-source.zip',metadata['dependencies'])
    (a.output/'PSX.bda').write_bytes(bda);shutil.copyfile(BUILD/'PSX.build.json',a.output/'PSX.build.json')
    shutil.copyfile(ROOT/f'docs/release-v{v}.md',a.output/'RELEASE-NOTES.md')
    record={'version':v,'application_commit':manifest['application_commit'],'dependencies':metadata['dependencies'],
            'bda_sha256':metadata['sha256'],'exact_bda_hardware_tested':False,'full_firmware_in_ci':False,
            'runtime_scope':'Actual release MIPS with H1 services and JZ4740 register models; no new device benchmark',
            'checks':reports,'clock_backend_model':clock,'prior_physical_408_evidence':read_json(ROOT/'docs/evidence/prior-408.json')}
    write_json(a.output/'release-manifest.json',record)
    install={'应用/程序/PSX.bda':bda,'PS1/H1TEST.exe':(ROOT/'build/test-rom/H1TEST.exe').read_bytes(),
             'README.md':(ROOT/'README.md').read_bytes(),'NOTICE.md':(ROOT/'NOTICE.md').read_bytes(),
             'LICENSE':(ROOT/'LICENSE').read_bytes(),'PSX.build.json':(a.output/'PSX.build.json').read_bytes()}
    for name,path in [('PCSX4ALL-gpl.txt','third_party/pcsx4all/gpl.txt'),('Zlib-LICENSE.txt','third_party/zlib/LICENSE'),('H1-SDK-LICENSE.txt','sdk/LICENSE'),('H1-SDK-NOTICE.txt','sdk/NOTICE')]:install['LICENSES/'+name]=(ROOT/path).read_bytes()
    install['LICENSES/NotoSansCJK-OFL.txt']=(ROOT/'assets/licenses/NotoSansCJK-OFL.txt').read_bytes()
    recompiler=(ROOT/'third_party/pcsx4all/src/recompiler/mips/recompiler.cpp').read_bytes();install['LICENSES/MIPS-recompiler-MIT.txt']=recompiler.split(b'#include',1)[0]
    with zipfile.ZipFile(a.output/f'BBKH1-PS1-v{v}-install.zip','w') as z:
        for name,data in sorted(install.items()):add(z,name,data)
    (a.output/'SHA256SUMS.txt').write_text(''.join(digest(p.read_bytes())+'  '+p.name+'\n' for p in sorted(a.output.iterdir()) if p.name!='SHA256SUMS.txt'),encoding='ascii')
    verify(a.output,a.tag,manifest['application_commit'])
if __name__=='__main__':main()
