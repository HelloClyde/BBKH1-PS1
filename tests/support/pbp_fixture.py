"""Original PS1 sectors in a popstation-compatible PBP; no Sony/game bytes."""
import random
import struct
import zlib

SECTOR = 2352
BLOCK = 16 * SECTOR


def bcd(n):
    return (n//10)*16+n%10


def msf(n):
    m, rem = divmod(n, 4500)
    s, f = divmod(rem, 75)
    return bytes(map(bcd, (m, s, f)))


def sector(value):
    raw = bytearray([value]*SECTOR)
    raw[15] = 2
    return bytes(raw)


def disc_image(sectors, audio_at=None, stored=(), data_offset=0x100000):
    image = bytearray(data_offset)
    image[:12] = b'PSISOIMG0000'
    image[0x400:0x40b] = b'_H1XX_00001'
    struct.pack_into('<I', image, 0xbfc, data_offset)
    toc = [bytes([0x41, 0, 0xa0, 0, 0, 0, 0, 1, 0x20, 0]),
           bytes([0x41, 0, 0xa1, 0, 0, 0, 0, 2 if audio_at else 1, 0, 0]),
           bytes([0x41, 0, 0xa2, 0, 0, 0, 0])+msf(len(sectors)),
           bytes([0x41, 0, 1])+msf(151)+b'\0'+msf(150)]
    if audio_at:
        first, start = audio_at
        toc.append(bytes([1, 0, 2])+msf(first)+b'\0'+msf(start))
    image[0x800:0x800+10*len(toc)] = b''.join(toc)
    raw = b''.join(sectors)
    raw += bytes((-len(raw)) % BLOCK)
    for block in range(len(raw)//BLOCK):
        content = raw[block*BLOCK:(block+1)*BLOCK]
        compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
        packed = compressor.compress(content)+compressor.flush()
        if block in stored or len(packed) >= BLOCK:
            packed = content
        offset = len(image)-data_offset
        # The high half-word is a flag, not part of the compressed length.
        struct.pack_into('<IHH', image, 0x4000+block*32, offset, len(packed), 1)
        image.extend(packed)
        image.extend(bytes(17))  # gaps must not become part of the preceding block
    return bytes(image)


def pbp(discs, psar=0x40):
    header = bytearray(psar)
    header[:4] = b'\0PBP'
    struct.pack_into('<9I', header, 4, 0x10000, *([40]*7), psar)
    if len(discs) == 1:
        return bytes(header)+discs[0]
    title = bytearray(0x400)
    title[:16] = b'PSTITLEIMG000000'
    for i, disc in enumerate(discs):
        struct.pack_into('<I', title, 0x200+i*4, len(title))
        title.extend(disc)
    return bytes(header)+title


def selftest_disc(exe):
    """Minimal original ISO9660 with SYSTEM.CNF and the project's own EXE."""
    def directory(name, extent, size, flags=0):
        n = 33+len(name)+(len(name)%2 == 0)
        entry = bytearray(n)
        entry[0] = n
        struct.pack_into('<I', entry, 2, extent)
        struct.pack_into('>I', entry, 6, extent)
        struct.pack_into('<I', entry, 10, size)
        struct.pack_into('>I', entry, 14, size)
        entry[25] = flags
        entry[28:32] = b'\1\0\0\1'
        entry[32] = len(name)
        entry[33:33+len(name)] = name
        return entry
    blocks = [bytearray(2048) for _ in range(32+(len(exe)+2047)//2048)]
    vd = blocks[16]
    vd[:7] = b'\1CD001\1'
    vd[40:72] = b'H1 ORIGINAL TEST'.ljust(32)
    struct.pack_into('<I', vd, 80, len(blocks))
    struct.pack_into('>I', vd, 84, len(blocks))
    vd[128:132] = b'\0\10\10\0'
    vd[156:190] = directory(b'\0', 20, 2048, 2)
    blocks[17][:7] = b'\xffCD001\1'
    config = b'BOOT = cdrom:\\H1TEST.EXE;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFF00\r\n'
    records = b''.join([directory(b'\0', 20, 2048, 2), directory(b'\1', 20, 2048, 2),
                        directory(b'SYSTEM.CNF;1', 21, len(config)), directory(b'H1TEST.EXE;1', 24, len(exe))])
    blocks[20][:len(records)] = records
    blocks[21][:len(config)] = config
    for offset in range(0, len(exe), 2048):
        blocks[24+offset//2048][:len(exe[offset:offset+2048])] = exe[offset:offset+2048]
    sectors = []
    for i, data in enumerate(blocks):
        raw = bytearray(SECTOR)
        raw[1:11] = b'\xff'*10
        raw[12:15] = msf(i+150)
        raw[15] = 2
        raw[24:24+2048] = data
        sectors.append(bytes(raw))
    return disc_image(sectors)
