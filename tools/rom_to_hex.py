#!/usr/bin/env python3
"""Convert mapper-0/4/16 iNES files to hex or startup-decompressed SmileBASIC programs."""
import argparse
import base64
from collections import defaultdict, deque
from pathlib import Path

MAX_ROM = 16 + 512 + 524288 + 262144
MAX_PROGRAM_CHARS = 1048576

def validate(data: bytes) -> None:
    if len(data) < 16 or data[:4] != b'NES\x1a':
        raise ValueError('expected an iNES header')
    if data[7] & 12 == 8:
        raise ValueError('NES 2.0 is not supported')
    mapper = (data[6] >> 4) | (data[7] & 240)
    if mapper not in (0, 4, 16):
        raise ValueError(f'mapper {mapper} is not supported; supported: 0 (NROM), 4 (MMC3), 16 (Bandai FCG)')
    if data[7] & 3:
        raise ValueError('VS/PlayChoice ROMs are not supported')
    if mapper == 0:
        if data[4] not in (1, 2) or data[5] not in (0, 1):
            raise ValueError('NROM requires 16/32 KiB PRG and 0/8 KiB CHR')
    elif mapper == 16:
        if data[4] not in (1, 2, 4, 8, 16) or data[5] not in (0, 1, 2, 4, 8, 16, 32):
            raise ValueError("Bandai FCG requires power-of-two 16-256 KiB PRG and 0/8-256 KiB CHR")
    else:
        if data[4] not in (2, 4, 8, 16, 32) or data[5] not in (0, 1, 2, 4, 8, 16, 32):
            raise ValueError('MMC3 requires power-of-two 32-512 KiB PRG and 0/8-256 KiB CHR')
    if data[8] > 1:
        raise ValueError('only 8 KiB PRG RAM is supported')
    if data[9] & 1:
        raise ValueError('PAL is not supported')
    size = 16 + (512 if data[6] & 4 else 0) + data[4]*16384 + data[5]*8192
    if len(data) != size:
        raise ValueError(f'expected exactly {size} bytes, got {len(data)}')

def decode(text: str) -> bytes:
    compact = ''.join(c for c in text if c in '0123456789abcdefABCDEF')
    if any(c not in '0123456789abcdefABCDEF \t\r\n' for c in text):
        raise ValueError('only hex digits and ASCII whitespace are accepted')
    if len(compact) % 2:
        raise ValueError('odd hex digit count')
    return bytes.fromhex(compact)

def encode(data: bytes, fmt: str = 'hex', width: int = 32) -> str:
    validate(data)
    rows = [data[i:i+width].hex().upper() for i in range(0,len(data),width)]
    if fmt == 'data':
        return '@ROMHEX\n' + '\n'.join(f'DATA "{row}"' for row in rows) + '\nDATA "END"\n'
    return '\n'.join(rows)+'\n'

def pack(data: bytes) -> bytes:
    """LZ stream: literal token 0..127 + 1 bytes, match 128..255 + 3 bytes.

    Matches store a little-endian distance, and may overlap their output.
    """
    positions = defaultdict(lambda: deque(maxlen=32))
    out = bytearray()
    literals = bytearray()
    def flush():
        if literals:
            out.append(len(literals)-1)
            out.extend(literals)
            literals.clear()
    i = 0
    while i < len(data):
        key = data[i:i+3]
        length = distance = 0
        for previous in reversed(positions[key]):
            if i-previous > 65535:
                break
            n = 0
            while n < min(130, len(data)-i) and data[previous+n] == data[i+n]:
                n += 1
            if n > length:
                length, distance = n, i-previous
            if length == 130:
                break
        count = length if length >= 3 else 1
        if length >= 3:
            flush()
            out.extend((128+length-3, distance & 255, distance >> 8))
        else:
            literals.append(data[i])
            if len(literals) == 128:
                flush()
        for j in range(i, i+count):
            positions[data[j:j+3]].append(j)
        i += count
    flush()
    return bytes(out)


def embedded(data: bytes) -> str:
    validate(data)
    payload = base64.b64encode(pack(data)).decode('ascii').rstrip('=')
    return ('@ROMHEX\nDATA "LZ64"\nDATA '+str(len(data))+'\n' +
            ''.join('DATA "'+payload[i:i+128]+'"\n' for i in range(0,len(payload),128)) +
            'DATA "END"\n')


def program(data: bytes) -> str:
    source = (Path(__file__).resolve().parents[1]/'NES.bas').read_text()
    output = source.split('\n@ROMHEX\n')[0]+'\n'+embedded(data)
    if len(output) > MAX_PROGRAM_CHARS:
        raise ValueError('embedded program exceeds SmileBASIC 1,048,576-character limit; use TXT hex loading')
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--format', choices=['hex','data','program'], default='hex')
    args = parser.parse_args()
    try:
        data = args.rom.read_bytes()
        if args.format == 'program':
            output = program(data)
        else:
            output = embedded(data) if args.format == 'data' else encode(data,args.format)
        args.output.write_text(output, encoding='ascii')
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')

if __name__ == '__main__':
    main()
