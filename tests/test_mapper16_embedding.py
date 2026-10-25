"""Exercise mapper 16 and the actual startup decoder in generated BASIC."""
import base64
import random
import re
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from basic_vm import BasicVM
from rom_to_hex import pack, embedded, program, validate

class LoaderVM(BasicVM):
    """Add only DATA/string operations needed by the startup loader."""
    def __init__(self,source):
        super().__init__(source)
        self.strings={}
        rows=source.split('\n@ROMHEX\n')[1].splitlines()
        self.data=iter(line[5:].strip() for line in rows if line.startswith('DATA '))
    def expr(self,text):
        text=re.sub(r'MID\$\((\w+\$),([^,]+),([^()]+)\)',lambda m:repr(self.strings[m[1]][int(super(LoaderVM,self).expr(m[2])):int(super(LoaderVM,self).expr(m[2]))+int(super(LoaderVM,self).expr(m[3]))]),text)
        text=re.sub(r"ASC\(('.*?')\)",lambda m:str(ord(eval(m[1]))),text)
        text=re.sub(r'LEN\((\w+\$)\)',lambda m:str(len(self.strings[m[1]])),text)
        text=re.sub(r'\b\w+\$',lambda m:repr(self.strings.get(m[0],'')),text)
        if "'" in text or '"' in text:
            return eval(text.replace(' OR ',' or ').replace(' AND ',' and '),{'__builtins__':{}},{})
        return super().expr(text)
    def inline(self,line):
        if line.startswith('RESTORE @ROMHEX'): return False
        if line.startswith('READ '):
            first,sep,rest=line.partition(':')
            name=first[5:]
            value=next(self.data)
            if name.endswith('$'): self.strings[name]=value.strip('"')
            else:self.v[name]=int(value)
            return self.inline(rest) if sep else False
        if not line.startswith('IF ') and re.match(r'^\w+\$=',line):
            first,sep,rest=line.partition(':')
            name,value=first.split('=',1);self.strings[name]=self.expr(value)
            return self.inline(rest) if sep else False
        return super().inline(line)


def decode_embedded(block):
    source=(ROOT/'NES.bas').read_text().split('\n@ROMHEX\n')[0]+'\n'+block
    vm=LoaderVM(source)
    next(vm.data)
    vm.call('UNPACK')
    return bytes(vm.a['ROM'][:vm.v['N']])

class EmbeddingTests(unittest.TestCase):
    def test_basic_decoder_roundtrips(self):
        rng=random.Random(16)
        for data in (bytes(range(256))*4,bytes(4096),rng.randbytes(2049),b'abc'*1000):
            payload=base64.b64encode(pack(data)).decode().rstrip('=')
            # Vary DATA boundaries independently of token and Base64 groups.
            block='@ROMHEX\nDATA "LZ64"\nDATA '+str(len(data))+'\n'+''.join('DATA "'+payload[i:i+31]+'"\n' for i in range(0,len(payload),31))+'DATA "END"\n'
            self.assertEqual(decode_embedded(block),data)
    def test_decoder_rejects_bad_distance_and_truncation(self):
        for stream in (bytes([128,0,0]),bytes([128,1,0]),bytes([127,1])):
            block='@ROMHEX\nDATA "LZ64"\nDATA 16\nDATA "'+base64.b64encode(stream).decode().rstrip('=')+'"\nDATA "END"\n'
            with self.assertRaises(RuntimeError):decode_embedded(block)

class Mapper16Tests(unittest.TestCase):
    def setUp(self):
        self.vm=BasicVM((ROOT/'NES.bas').read_text())
        data=(b'NES\x1a'+bytes([16,32,0,16,0,0,0,0,0,0,0,0])+
              b''.join(bytes([i])*8192 for i in range(32))+
              b''.join(bytes([i])*1024 for i in range(256)))
        validate(data);self.vm.a['ROM'][:len(data)]=data;self.vm.v['N']=len(data)
        self.vm.call('VALIDATE');self.vm.call('CARTINIT')
    def write(self,a,v):
        self.vm.v.update(AD=a,WV=v);self.vm.call('WRITE')
    def read(self,a):
        self.vm.v['AD']=a;self.vm.call('READ');return self.vm.v['RV']
    def test_banks_and_aliases(self):
        self.assertEqual([self.read(a) for a in (0x8000,0xA000,0xC000,0xFFFF)],[0,1,30,31])
        self.write(0x7FF8,5)
        self.assertEqual(self.read(0x8000),10)
        self.write(0xFFF8,0xFF);self.assertEqual(self.read(0x8000),30)
        for i in range(8):
            self.write(0x8000+i,255-i)
            self.vm.v['PA']=i*1024;self.vm.call('PREAD')
            self.assertEqual(self.vm.v['PB'],255-i)
        self.assertEqual(self.read(0x6000),16)
    def test_all_mirroring_modes(self):
        for mode,expected in enumerate(([0,1,0,1],[0,0,1,1],[0,0,0,0],[1,1,1,1])):
            self.write(0x8009,mode)
            actual=[]
            for i in range(4):
                self.vm.v['PA']=0x2000+1024*i;self.vm.call('PMAP')
                actual.append((self.vm.v['PA']-8192)//1024)
            self.assertEqual(actual,expected)
    def test_cycle_irq_latch_direct_and_ack(self):
        v=self.vm.v
        self.write(0x800B,2);self.write(0x800C,1);self.write(0x800A,1)
        self.assertEqual(v['IRQCOUNT'],258)
        v.update(CC=258,LINE=240,DOT=1);self.vm.call('ADVANCE')
        self.assertEqual((v['IRQCOUNT'],v['MIRQ']),(0,0))
        v['CC']=1;self.vm.call('ADVANCE')
        self.assertEqual((v['IRQCOUNT'],v['MIRQ']),(65535,1))
        self.write(0x800A,0);self.assertEqual(v['MIRQ'],0)
        self.write(0x600B,5);self.write(0x600C,0);self.write(0x600A,1)
        self.assertEqual(v['IRQCOUNT'],5)
        v['CC']=6;self.vm.call('ADVANCE');self.assertEqual(v['MIRQ'],1)

class EEPROMTests(unittest.TestCase):
    setUp=Mapper16Tests.setUp
    write=Mapper16Tests.write
    read=Mapper16Tests.read
    def pin(self,clock,data=0,read=False):
        self.write(0x800D,clock*32+data*64+int(read)*128)
    def start(self):
        for c,d in ((0,0),(0,1),(1,1),(1,0),(0,0)):self.pin(c,d)
    def stop(self):
        for c,d in ((0,0),(1,0),(1,1),(0,1)):self.pin(c,d)
    def send(self,value):
        for bit in range(8):
            d=(value>>bit)&1
            self.pin(0,d);self.pin(1,d);self.pin(0,d)
        self.pin(0,1,True);self.pin(1,1,True)
        self.assertEqual(self.read(0x6000)&16,0,'EEPROM must acknowledge')
        self.pin(0,0)
    def receive(self,ack=False):
        value=0
        for bit in range(8):
            self.pin(1,1,True)
            value|=((self.read(0x6000)>>4)&1)<<bit
            self.pin(0,1,True)
        self.pin(0,int(not ack));self.pin(1,int(not ack));self.pin(0,int(not ack))
        return value
    def test_serial_write_read_and_sequential_address(self):
        self.start();self.send(126);self.send(0x96);self.send(0x3D);self.send(0xA5);self.stop()
        self.assertEqual(self.vm.a['SRAM'][:1],[0xA5])
        self.start();self.send(126|128)
        self.assertEqual(self.receive(True),0x96)
        self.assertEqual(self.receive(True),0x3D)
        self.assertEqual(self.receive(),0xA5)
        self.stop();self.assertEqual(self.read(0x6000),16)
    def test_stop_aborts_partial_byte(self):
        self.start();self.pin(1,1);self.pin(0,1);self.stop()
        self.assertEqual(self.vm.a['SRAM'][0],0)
        self.start();self.send(3);self.send(0x42);self.stop()
        self.assertEqual(self.vm.a['SRAM'][3],0x42)
