"""Fetch pinned dependencies without resetting or editing existing checkouts."""
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[1]

def main():
    dependencies=json.loads((ROOT/'UPSTREAM.json').read_text())
    for key,info in dependencies.items():
        target=(ROOT/info['path']).resolve() if 'path' in info else ROOT/'third_party'/key
        if target.exists():
            print(f'Keeping existing {target}; build.py verifies its commit and tracked files.')
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','clone','--no-checkout',info['url'],str(target)],check=True)
        subprocess.run(['git','-C',str(target),'checkout','--detach',info['commit']],check=True)
if __name__=='__main__':main()
