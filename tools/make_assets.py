"""Build the redistributable PS-X EXE (no Sony SDK/BIOS)."""
from pathlib import Path
import os,struct,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
    # The imagegen-designed PSX icon is checked in; builds never regenerate it.
    if '--regenerate-icon' in __import__('sys').argv:
        raise SystemExit('The PSX icon is a checked-in imagegen asset. See assets/README.md and assets/icon-prompt.txt.')
    make_guest()

def make_guest():
    build=ROOT/'build/test-rom';build.mkdir(parents=True,exist_ok=True)
    src=ROOT/'tests/test_guest.S';elf=build/'test.elf';raw=build/'test.bin'
    tc=Path(os.environ.get('H1_GNU_BIN',ROOT/'.tools/toolchain/bin'))
    subprocess.run([str(tc/'mipsel-none-elf-gcc.exe'),'-EL','-march=mips1','-mfp32','-msoft-float','-mno-abicalls','-G0','-fno-pic','-nostdlib','-Wl,--build-id=none','-Wl,-Ttext=0x80010000','-Wl,-e,_start','-o',str(elf),str(src)],check=True)
    subprocess.run([str(tc/'mipsel-none-elf-objcopy.exe'),'-O','binary','-j','.text',str(elf),str(raw)],check=True)
    data=raw.read_bytes();data+=bytes((-len(data))%2048)
    header=bytearray(2048);header[:8]=b'PS-X EXE';struct.pack_into('<4I',header,0x10,0x80010000,0,0x80010000,len(data));struct.pack_into('<I',header,0x30,0x801fff00)
    (build/'H1TEST.exe').write_bytes(header+data)
    print(build/'H1TEST.exe')
if __name__=='__main__':main()
