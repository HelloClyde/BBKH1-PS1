"""Build the documented release configuration without a device connection."""
import subprocess,sys
from release_config import ROOT,OPTIONS
for name,args in [('make_assets.py',[]),('build.py',OPTIONS)]:
    subprocess.run([sys.executable,str(ROOT/'tools'/name),*args],check=True)
