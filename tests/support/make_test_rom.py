"""Create original ARM homebrew testing RGB565, keyboard A and SRAM.

No proprietary BIOS/header logo bytes are included. gpSP accepts this header.
The first pixel is green while A is pressed, blue otherwise; all others are red.
"""
from pathlib import Path
import struct

def make_rom(tone=False):
    words, labels, fixups, literals = [], {}, [], []
    def emit(x): words.append(x)
    def label(name): labels[name] = len(words) * 4
    def ldr(reg, value):
        literals.append((len(words), reg, value)); emit(0)
    def branch(name, cond=14):
        fixups.append((len(words), name, cond)); emit(0)
    ldr(0, 0x04000000); ldr(1, 0x403); emit(0xe1c010b0)  # mode 3, BG2
    ldr(0, 0x06000000); emit(0xe3a0101f); ldr(2, 240 * 160)
    label('fill'); emit(0xe0c010b2); emit(0xe2522001); branch('fill', 1)
    ldr(0, 0x0e000000); emit(0xe3a0105a); emit(0xe5c01000)  # SRAM[0] = 5A
    if tone:
        # GBA PSG channel 1: continuous 1024 Hz, 50% duty, both speakers.
        for address, value in [(0x04000084, 0x80), (0x04000080, 0x1177),
                               (0x04000082, 2), (0x04000060, 0),
                               (0x04000062, 0xf080), (0x04000064, 0x8780)]:
            ldr(0, address); ldr(1, value); emit(0xe1c010b0)
    ldr(0, 0x04000130); ldr(3, 0x06000000)
    label('loop'); emit(0xe1d020b0); emit(0xe3120001)
    ldr(1, 0x7c00); branch('put', 1)  # released: blue
    ldr(1, 0x03e0)
    label('put'); emit(0xe1c310b0); branch('loop')
    for i, reg, value in literals:
        offset = len(words) * 4 - (i * 4 + 8)
        words[i] = 0xe59f0000 | reg << 12 | offset
        words.append(value)
    for i, target, cond in fixups:
        delta = (labels[target] - (i * 4 + 8)) // 4
        words[i] = cond << 28 | 0x0a000000 | (delta & 0xffffff)
    rom = bytearray(32768)
    struct.pack_into('<I', rom, 0, 0xea00002e)  # branch to 0xc0
    rom[0xa0:0xac] = b'H1TEST      '
    rom[0xac:0xb0] = b'H1TE'; rom[0xb0:0xb2] = b'00'; rom[0xb2] = 0x96
    rom[0xbd] = (-sum(rom[0xa0:0xbd]) - 0x19) & 255
    rom[0xc0:0xc0 + len(words) * 4] = struct.pack('<' + 'I' * len(words), *words)
    rom[0x200:0x20b] = b'SRAM_V113\0\0'
    return bytes(rom)

if __name__ == '__main__':
    p = Path(__file__).resolve().parents[1] / 'build/test-rom/H1TEST.gba'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(make_rom()); print(p)
