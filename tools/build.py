"""Generate the opcode tables and distributable SmileBASIC source."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Each row: mnemonic followed by opcode/addressing-mode/base-cycles.
# A trailing + denotes an indexed-read page-cross penalty.
SPEC = '''
ADC 69:imm:2 65:zp:3 75:zpx:4 6D:abs:4 7D:abx:4+ 79:aby:4+ 61:inx:6 71:iny:5+
AND 29:imm:2 25:zp:3 35:zpx:4 2D:abs:4 3D:abx:4+ 39:aby:4+ 21:inx:6 31:iny:5+
ASL 0A:acc:2 06:zp:5 16:zpx:6 0E:abs:6 1E:abx:7
BCC 90:rel:2
BCS B0:rel:2
BEQ F0:rel:2
BIT 24:zp:3 2C:abs:4
BMI 30:rel:2
BNE D0:rel:2
BPL 10:rel:2
BRK 00:imp:7
BVC 50:rel:2
BVS 70:rel:2
CLC 18:imp:2
CLD D8:imp:2
CLI 58:imp:2
CLV B8:imp:2
CMP C9:imm:2 C5:zp:3 D5:zpx:4 CD:abs:4 DD:abx:4+ D9:aby:4+ C1:inx:6 D1:iny:5+
CPX E0:imm:2 E4:zp:3 EC:abs:4
CPY C0:imm:2 C4:zp:3 CC:abs:4
DEC C6:zp:5 D6:zpx:6 CE:abs:6 DE:abx:7
DEX CA:imp:2
DEY 88:imp:2
EOR 49:imm:2 45:zp:3 55:zpx:4 4D:abs:4 5D:abx:4+ 59:aby:4+ 41:inx:6 51:iny:5+
INC E6:zp:5 F6:zpx:6 EE:abs:6 FE:abx:7
INX E8:imp:2
INY C8:imp:2
JMP 4C:abs:3 6C:ind:5
JSR 20:abs:6
LDA A9:imm:2 A5:zp:3 B5:zpx:4 AD:abs:4 BD:abx:4+ B9:aby:4+ A1:inx:6 B1:iny:5+
LDX A2:imm:2 A6:zp:3 B6:zpy:4 AE:abs:4 BE:aby:4+
LDY A0:imm:2 A4:zp:3 B4:zpx:4 AC:abs:4 BC:abx:4+
LSR 4A:acc:2 46:zp:5 56:zpx:6 4E:abs:6 5E:abx:7
NOP EA:imp:2
ORA 09:imm:2 05:zp:3 15:zpx:4 0D:abs:4 1D:abx:4+ 19:aby:4+ 01:inx:6 11:iny:5+
PHA 48:imp:3
PHP 08:imp:3
PLA 68:imp:4
PLP 28:imp:4
ROL 2A:acc:2 26:zp:5 36:zpx:6 2E:abs:6 3E:abx:7
ROR 6A:acc:2 66:zp:5 76:zpx:6 6E:abs:6 7E:abx:7
RTI 40:imp:6
RTS 60:imp:6
SBC E9:imm:2 E5:zp:3 F5:zpx:4 ED:abs:4 FD:abx:4+ F9:aby:4+ E1:inx:6 F1:iny:5+
SEC 38:imp:2
SED F8:imp:2
SEI 78:imp:2
STA 85:zp:3 95:zpx:4 8D:abs:4 9D:abx:5 99:aby:5 81:inx:6 91:iny:6
STX 86:zp:3 96:zpy:4 8E:abs:4
STY 84:zp:3 94:zpx:4 8C:abs:4
TAX AA:imp:2
TAY A8:imp:2
TSX BA:imp:2
TXA 8A:imp:2
TXS 9A:imp:2
TYA 98:imp:2
'''
MODES = 'imp acc imm zp zpx zpy abs abx aby inx iny ind rel'.split()
OPS = [line.split()[0] for line in SPEC.strip().splitlines()]

def table():
    result = {}
    for line in SPEC.strip().splitlines():
        op, *entries = line.split()
        for entry in entries:
            code, mode, cycles = entry.split(':')
            result[int(code,16)] = (op, mode, int(cycles.rstrip('+')), int(cycles.endswith('+')))
    assert len(result) == 151
    return result

def build():
    entries = table()
    out = []
    for code in range(256):
        op, mode, cycles, penalty = entries.get(code, (None,'imp',0,0))
        out.append(f'DATA {OPS.index(op)+1 if op else 0},{MODES.index(mode)},{cycles},{penalty}')
    def dispatch_tree(variable, targets, first=0):
        # Nested branches keep the number of comparisons logarithmic.
        if len(targets) == 1:
            return f'GOSUB @{targets[0]}:RETURN'
        middle = len(targets) // 2
        left = dispatch_tree(variable, targets[:middle], first)
        right = dispatch_tree(variable, targets[middle:], first + middle)
        return (f'IF {variable}<{first + middle} THEN\n' + left +
                '\nELSE\n' + right + '\nENDIF')
    dispatch = dispatch_tree('K', [f'O_{op}' for op in OPS], 1)
    modes = dispatch_tree('MD', [f'M_{mode.upper()}' for mode in MODES])
    core = (ROOT/'src/core.bas').read_text()
    core = core.replace("' OPCODE_DISPATCH", dispatch).replace("' MODE_DISPATCH", modes)
    core = core.replace("' OPCODE_DATA", '\n'.join(out))
    from make_diagnostic import diagnostic
    from rom_to_hex import encode
    core = core.split('\n@ROMHEX\n')[0] + '\n' + encode(diagnostic(), 'data')
    (ROOT/'NES.bas').write_text(core)

if __name__ == '__main__':
    build()
