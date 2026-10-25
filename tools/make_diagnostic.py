"""Original, freely usable NROM/CHR-RAM diagnostic; no game ROM needed."""
from pathlib import Path
from rom_to_hex import encode

def diagnostic():
    code = bytearray()
    labels = {}
    patches = []
    def emit(*values): code.extend(values)
    def label(name): labels[name] = 0x8000 + len(code)
    def branch(op, name):
        emit(op, 0); patches.append((len(code)-1, name, 'rel'))
    def jump(op, name):
        emit(op, 0, 0); patches.append((len(code)-2, name, 'abs'))
    def write(addr, value): emit(0xA9,value,0x8D,addr&255,addr>>8)
    def ppuaddr(addr): write(0x2006,addr>>8); write(0x2006,addr&255)
    label('reset')
    emit(0x78,0xD8,0xA2,0xFF,0x9A,0xE8,0x8E,0,0x20,0x8E,1,0x20)
    label('wait'); emit(0x2C,2,0x20); branch(0x10,'wait')
    ppuaddr(0)
    for value in [0xAA,0x55]*4+[0x00]*8:
        write(0x2007,value)
    ppuaddr(0x3F00)
    for value in [0x0F,0x21,0x30,0x16]: write(0x2007,value)
    ppuaddr(0x2000)
    emit(0xA0,4,0xA2,0,0xA9,0)
    label('clear'); emit(0x8D,7,0x20,0xE8); branch(0xD0,'clear')
    emit(0x88); branch(0xD0,'clear')
    write(0x2005,0); write(0x2005,0); write(0x2000,0x80); write(0x2001,0x0A)
    label('forever'); jump(0x4C,'forever')
    label('nmi'); emit(0x48,0xE6,0,0xAD,2,0x20)
    ppuaddr(0x3F01)
    emit(0xA5,0,0x29,0x3F,0x8D,7,0x20)
    write(0x2005,0); write(0x2005,0)
    emit(0x68,0x40)
    label('irq'); emit(0x40)
    for offset,name,kind in patches:
        addr=labels[name]
        if kind=='abs': code[offset:offset+2]=addr.to_bytes(2,'little')
        else:
            delta=addr-(0x8000+offset+1)
            assert -128<=delta<=127
            code[offset]=delta&255
    prg=bytearray([0xEA])*16384
    prg[:len(code)]=code
    for offset,name in [(0x3FFA,'nmi'),(0x3FFC,'reset'),(0x3FFE,'irq')]:
        prg[offset:offset+2]=labels[name].to_bytes(2,'little')
    return b'NES\x1a'+bytes([1,0,0,0,0,0,0,0,0,0,0,0])+prg

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    data=diagnostic()
    (root/'examples/diagnostic.hex').write_text(encode(data))
    (root/'examples/diagnostic_data.bas').write_text(encode(data,'data'))
