"""Inspect an existing PS1 raw/ISO image and optionally extract its boot EXE.

For local diagnostics only. Extracted commercial executables are not included
in emulator packages.
"""
from pathlib import Path
import argparse,json,re,struct

class Disc:
    def __init__(self,path):
        self.file=Path(path).open('rb');self.stride=2048 if Path(path).suffix.lower()=='.iso' else 2352
    def sector(self,n):
        self.file.seek(n*self.stride);b=self.file.read(self.stride)
        if len(b)!=self.stride:raise ValueError(f'Sector {n} outside image')
        if self.stride==2048:return b
        if b[15]==1:return b[16:2064]
        if b[15]==2:return b[24:2072]
        raise ValueError('Not a data sector')
    def read(self,lba,size):return b''.join(self.sector(lba+i) for i in range((size+2047)//2048))[:size]
    def directory(self,lba,size):
        b=self.read(lba,size);i=0;items=[]
        while i<len(b):
            n=b[i]
            if n==0:i=(i//2048+1)*2048;continue
            r=b[i:i+n]
            if len(r)<34:raise ValueError('Truncated ISO directory')
            name=r[33:33+r[32]].decode('ascii',errors='replace')
            items.append({'name':name,'lba':struct.unpack_from('<I',r,2)[0],
                          'size':struct.unpack_from('<I',r,10)[0],'directory':bool(r[25]&2)})
            i+=n
        return items
    def boot(self):
        pvd=self.sector(16)
        if pvd[1:6]!=b'CD001':raise ValueError('No ISO9660 primary descriptor')
        root=self.directory(struct.unpack_from('<I',pvd,158)[0],struct.unpack_from('<I',pvd,166)[0])
        cnf=next((r for r in root if r['name']=='SYSTEM.CNF;1'),None)
        config=self.read(cnf['lba'],cnf['size']).decode('ascii') if cnf else ''
        m=re.search(r'BOOT\s*=\s*cdrom:\\?([^\r\n]+)',config,re.I)
        name=m.group(1).strip().replace('/','\\').lstrip('\\') if m else 'PSX.EXE;1'
        entries=root;record=None
        for component in name.split('\\'):
            record=next(r for r in entries if r['name'].upper()==component.upper())
            if record['directory']:entries=self.directory(record['lba'],record['size'])
        data=self.read(record['lba'],record['size'])
        if data[:8]!=b'PS-X EXE':raise ValueError('Boot file is not PS-X EXE')
        return {'volume':pvd[40:72].decode('ascii').strip(),'config':config,'executable':record,
                'entry':struct.unpack_from('<I',data,0x10)[0],'load_address':struct.unpack_from('<I',data,0x18)[0],
                'load_size':struct.unpack_from('<I',data,0x1c)[0]},data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('disc',type=Path);p.add_argument('--extract-boot',type=Path);a=p.parse_args()
    disc=Disc(a.disc)
    try:info,data=disc.boot()
    finally:disc.file.close()
    if a.extract_boot:a.extract_boot.parent.mkdir(parents=True,exist_ok=True);a.extract_boot.write_bytes(data)
    print(json.dumps(info,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
