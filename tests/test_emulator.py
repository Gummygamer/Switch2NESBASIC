import random
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build import table, OPS, MODES, build
from make_diagnostic import diagnostic
from rom_to_hex import encode, decode, validate, MAX_ROM, program, MAX_PROGRAM_CHARS
from basic_vm import BasicVM

class EmulatorTests(unittest.TestCase):
    def setUp(self):
        self.vm=BasicVM((ROOT/'NES.bas').read_text())
        v=self.vm.v
        v.update(PRGO=16,PRGS=16384,CHRS=0,SP=253,PC=0x8000,FL=36)
        self.vm.a['ROM'][:16400]=diagnostic()
        self.vm.call('CARTINIT')
        for op,(name,mode,cycles,penalty) in table().items():
            for arr,value in [('OT',OPS.index(name)+1),('MT',MODES.index(mode)),('CT',cycles),('PT',penalty)]:
                self.vm.a[arr][op]=value
    def step(self,*code):
        offset=16+(self.vm.v['PC']-0x8000)%16384
        self.vm.a['ROM'][offset:offset+len(code)]=code
        self.vm.call('CPU')
    def test_hex_roundtrip(self):
        rom=diagnostic()
        self.assertEqual(decode(encode(rom)),rom)
        self.assertIn('DATA "END"',encode(rom,'data'))
        for text in ['0','0xFF','AB:CD','GG','AA\u00a0BB']:
            with self.assertRaises(ValueError): decode(text)
    def test_rom_validation(self):
        base=bytearray(diagnostic())
        for index,value in [(0,0),(4,3),(5,2),(6,16),(7,8),(7,1),(9,1)]:
            bad=base.copy();bad[index]=value
            with self.assertRaises(ValueError): validate(bad)
        with self.assertRaises(ValueError): validate(base[:-1])
        maximum=b'NES\x1a'+bytes([2,1,4,0,0,0,0,0,0,0,0,0])+bytes(512+32768+8192)
        validate(maximum);self.assertEqual(len(maximum),41488)
    def test_adc_sbc(self):
        rng=random.Random(6502)
        for opcode in (0x69,0xE9):
            for _ in range(1000):
                a,b,c=rng.randrange(256),rng.randrange(256),rng.randrange(2)
                v=self.vm.v;v.update(PC=0x8000,AC=a,FL=0x2C|c)
                self.step(opcode,b)
                operand=b if opcode==0x69 else b^255
                total=a+operand+c;result=total&255
                expected=(0x2C | int(total>255) | (result&128) | (2*int(result==0)) | ((~(a^operand)&(a^result)&128)>>1))
                self.assertEqual((v['AC'],v['FL'],v['CC']),(result,expected,2))
    def test_addressing_and_cycles(self):
        self.vm.v.update(XR=1)
        self.vm.a['ROM'][16+0x100]=0x77
        self.step(0xBD,0xFF,0x80)
        self.assertEqual((self.vm.v['AC'],self.vm.v['CC']),(0x77,5))
        self.vm.v.update(PC=0x8000,YR=2)
        self.vm.a['RAM'][255]=0xFE;self.vm.a['RAM'][0]=0x80
        self.step(0xB1,0xFF)
        self.assertEqual((self.vm.v['AC'],self.vm.v['CC']),(0x77,6))
    def test_indirect_jmp_wrap(self):
        self.vm.a['RAM'][0x2FF]=0x34;self.vm.a['RAM'][0x200]=0x12
        self.step(0x6C,0xFF,2)
        self.assertEqual(self.vm.v['PC'],0x1234)
    def test_stack_interrupts(self):
        self.step(0x20,0,0x90)
        self.assertEqual((self.vm.v['PC'],self.vm.v['SP']),(0x9000,251))
        self.step(0x60)
        self.assertEqual((self.vm.v['PC'],self.vm.v['SP']),(0x8003,253))
        v=self.vm.v;v.update(NMI=1,FL=0xA1)
        self.vm.call('CPU')
        self.assertEqual(v['CC'],7)
        self.assertEqual(self.vm.a['RAM'][0x1FB],0xA1)
        self.step(0x40)
        self.assertEqual((v['PC'],v['FL']),(0x8003,0xA1))
    def test_branch_wrap_page_cycles(self):
        self.vm.v.update(PC=0x80FE,FL=0x20)
        self.step(0xD0,0xFE)
        self.assertEqual((self.vm.v['PC'],self.vm.v['CC']),(0x80FE,4))
    def test_ppu_mirrors_buffer_and_status(self):
        v=self.vm.v
        def write(a,b):v.update(PA=a,PB=b);self.vm.call('PWRITE')
        def read(a):v['PA']=a;self.vm.call('PREAD');return v['PB']
        v['MIRROR']=1;write(0x2000,42)
        self.assertEqual(read(0x2800),42);self.assertEqual(read(0x3000),42)
        v['MIRROR']=0;self.assertEqual(read(0x2400),42)
        write(0x3F10,0x22);self.assertEqual(read(0x3F00),0x22)
        v.update(PV=0x2000,BUFFER=9,AD=0x2007)
        self.vm.call('READ');self.assertEqual(v['RV'],9)
        v['AD']=0x2007;self.vm.call('READ');self.assertEqual(v['RV'],42)
        v.update(STATUS=0xE0,BUS=7,AD=0x2002,WT=1)
        self.vm.call('READ');self.assertEqual((v['RV'],v['STATUS'],v['WT']),(0xE7,0x60,0))
    def test_controller_serial(self):
        v=self.vm.v;v.update(PAD=0xA5,AD=0x4016,WV=1)
        self.vm.call('WRITE');v.update(AD=0x4016,WV=0);self.vm.call('WRITE')
        bits=[]
        for _ in range(10):
            v['AD']=0x4016;self.vm.call('READ');bits.append(v['RV']&1)
        self.assertEqual(bits,[1,0,1,0,0,1,0,1,1,1])
    def test_all_official_opcodes_execute(self):
        for opcode in table():
            with self.subTest(opcode=hex(opcode)):
                self.vm.v.update(PC=0x8000,SP=253,NMI=0)
                self.step(opcode,0,0)
    def test_dma_wrap_and_stall(self):
        v=self.vm.v;v.update(AD=0x4014,WV=2,OA=250,CYCLES=1,CC=4)
        self.vm.a['RAM'][512:768]=list(range(256))
        self.vm.call('WRITE')
        self.assertEqual(self.vm.a['OAM'][250:],[0,1,2,3,4,5])
        self.assertEqual(self.vm.a['OAM'][:250],list(range(6,256)))
        self.assertEqual(v['CC'],518)
    def test_diagnostic_boot_and_render(self):
        v=self.vm.v;v['STATUS']=128
        for _ in range(5000): self.vm.call('CPU')
        self.assertEqual((v['CTRL'],v['MASK']),(128,10))
        self.assertEqual(self.vm.a['CHR'][:16],[0xAA,0x55]*4+[0]*8)
        # Palette-index colors make the rendered output easy to inspect.
        self.vm.a['COL']=list(range(64))
        v['LINE']=0;self.vm.call('DRAWLINE')
        self.assertEqual([self.vm.pixels[x,0] for x in range(8)],[33,15]*4)
        v.update(LINE=1,SCANV=4096);self.vm.call('DRAWLINE')
        self.assertEqual([self.vm.pixels[x,1] for x in range(8)],[15,33]*4)
        v['NMI']=1;self.vm.call('CPU')
        for _ in range(40): self.vm.call('CPU')
        self.assertEqual(self.vm.a['PAL'][1],1)
    def test_sprite_priority_flip_and_zero_hit(self):
        v=self.vm.v;v.update(LINE=1,SCANV=4096,MASK=30,CTRL=0)
        self.vm.a['COL']=list(range(64))
        self.vm.a['CHR'][1]=128  # background leftmost pixel, second row
        self.vm.a['CHR'][16]=128 # sprite tile 1, first row
        self.vm.a['PAL'][1]=2;self.vm.a['PAL'][17]=3
        self.vm.a['OAM'][:]=[255]*256
        self.vm.a['OAM'][:4]=[0,1,0,0]
        self.vm.call('DRAWLINE')
        self.assertEqual(self.vm.pixels[0,1],3)
        self.assertTrue(v['STATUS']&64)
        self.vm.a['OAM'][2]=32
        self.vm.call('DRAWLINE');self.assertEqual(self.vm.pixels[0,1],2)
        self.vm.a['OAM'][2]=64
        self.vm.call('DRAWLINE');self.assertEqual(self.vm.pixels[7,1],3)
    def test_generated_source_current(self):
        before=(ROOT/'NES.bas').read_bytes();build()
        self.assertEqual((ROOT/'NES.bas').read_bytes(),before)

if __name__=='__main__': unittest.main()
