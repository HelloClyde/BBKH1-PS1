"""Original icon and redistributable PS-X EXE (no Sony SDK/BIOS)."""
from pathlib import Path
import os,struct,subprocess
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
def main():
    # The original geometric icon is checked in; normal builds need no system font.
    if '--regenerate-icon' in __import__('sys').argv:
        make_icon()
    make_guest()

def make_icon():
    icon=Image.new('RGBA',(128,128),(0,0,0,0));d=ImageDraw.Draw(icon)
    d.rounded_rectangle((3,3,124,124),radius=24,fill='#34354b',outline='#b6b9d3',width=4)
    d.rounded_rectangle((15,18,112,76),radius=10,fill='#767c98',outline='#ecebff',width=2)
    d.ellipse((48,24,82,58),fill='#b6b9d3',outline='#f8f8ff',width=2)
    d.ellipse((61,37,69,45),fill='#34354b')
    font=ImageFont.load_default(size=31)
    d.text((29,80),'PS1',font=font,fill='white')
    icon.save(ROOT/'assets/icon.png')

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
