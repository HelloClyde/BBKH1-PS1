"""Build-independent regression entry point: never opens USB or serial ports."""
import json,os,subprocess,sys
from release_config import ROOT,BUILD

def run(*args):subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,check=True)
def main():
    bda=BUILD/'PSX.bda'
    run(ROOT/'tests/smoke.py',bda,'--stop-after','120','--output-dir',ROOT/'build/verification/smoke')
    run(ROOT/'tests/hud.py',bda)
    run(ROOT/'tests/turbo_frontend.py',bda)
    run(ROOT/'tests/release_runtime.py',bda)
    run(ROOT/'tests/pause_menu.py',bda)
    run(ROOT/'tests/pbp_runtime.py',bda)
    run(ROOT/'tests/settings.py',bda)
    run(ROOT/'tests/clock_control.py')
    run(ROOT/'tests/spu_samples.py',bda)
    run(ROOT/'tests/present_equivalence.py',bda)
    # Failure and sector-reader contracts need non-LTO callable functions.
    run(ROOT/'tools/build.py','--test-frames','6','--benchmark','--idle')
    contracts=ROOT/'build/jit-test6-bench-idle/PSX.bda'
    run(ROOT/'tests/smoke.py',contracts)
    run(ROOT/'tests/idle_equivalence.py',contracts)
    run(ROOT/'tests/disc_contract.py',contracts)
    run(ROOT/'tests/pbp_contract.py',contracts)
    run(ROOT/'tests/lifecycle.py',contracts)
    run(ROOT/'tests/frontend.py',bda,'--input-bda',contracts)
    run(ROOT/'tests/mapping.py',contracts)
    print('PASS compiled MIPS service/register-model checks; no device or full firmware test')
if __name__=='__main__':main()
