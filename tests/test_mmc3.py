"""Mapper tests run the generated BASIC implementation, not a Python mapper."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build import table,OPS,MODES
from rom_to_hex import validate,encode,decode,program,MAX_ROM,MAX_PROGRAM_CHARS
from basic_vm import BasicVM


def cartridge(prg=8,chr=16,flags=0,trainer=False):
    # Each 8K PRG and 1K CHR bank identifies itself at every address.
    header=b'NES\x1a'+bytes([prg,chr,0x40|flags|(4 if trainer else 0),0,0,0,0,0,0,0,0,0])
    return (header+(bytes(range(256))*2 if trainer else b'')+
            b''.join(bytes([i])*8192 for i in range(prg*2))+
            b''.join(bytes([i])*1024 for i in range(chr*8)))

class MMC3Tests(unittest.TestCase):
    def setUp(self):
        self.vm=BasicVM((ROOT/'NES.bas').read_text())
        for op,(name,mode,cycles,penalty) in table().items():
            for arr,value in [('OT',OPS.index(name)+1),('MT',MODES.index(mode)),('CT',cycles),('PT',penalty)]:
                self.vm.a[arr][op]=value
        self.load(cartridge())
    def load(self,data):
        validate(data)
        self.vm.a['ROM'][:len(data)]=data;self.vm.v['N']=len(data)
        self.vm.call('VALIDATE');self.vm.call('CARTINIT')
        self.vm.v.update(SP=253,FL=36)
    def write(self,addr,value):
        self.vm.v.update(AD=addr,WV=value);self.vm.call('WRITE')
    def read(self,addr):
        self.vm.v['AD']=addr;self.vm.call('READ');return self.vm.v['RV']
    def bank(self,register,value,mode=0):
        self.write(0x8000,mode|register);self.write(0x8001,value)
    def pread(self,addr):
        self.vm.v['PA']=addr;self.vm.call('PREAD');return self.vm.v['PB']
    def pwrite(self,addr,value):
        self.vm.v.update(PA=addr,PB=value);self.vm.call('PWRITE')
    def edge(self,time,high):
        self.vm.v.update(AT=time,AV=4096*high);self.vm.call('A12')
    def test_prg_modes_masking_and_register_aliases(self):
        self.assertEqual([self.read(a) for a in (0x8000,0xA000,0xC000,0xE000)],[0,1,14,15])
        self.bank(6,5);self.bank(7,9)
        self.assertEqual([self.read(a) for a in (0x8000,0xA000,0xC000,0xE000)],[5,9,14,15])
        self.write(0x9FFE,0x46)
        self.assertEqual([self.read(a) for a in (0x8000,0xA000,0xC000,0xE000)],[14,9,5,15])
        self.write(0x9FFF,0xFF) # 6-bit register, then absent chip address lines wrap
        self.assertEqual(self.read(0xC000),15)
        self.assertEqual(self.read(0xFFFF),15)
    def test_chr_modes_even_alignment_and_physical_reads(self):
        for reg,value in enumerate((11,23,31,42,53,64)): self.bank(reg,value)
        expected=[10,11,22,23,31,42,53,64]
        self.assertEqual([self.pread(i*1024) for i in range(8)],expected)
        self.write(0x8000,0x80)
        self.assertEqual([self.pread(i*1024+1023) for i in range(8)],expected[4:]+expected[:4])
        self.bank(2,255,0x80);self.assertEqual(self.pread(0),127)
        self.pwrite(0,9);self.assertEqual(self.pread(0),127) # ROM is immutable
    def test_banked_chr_ram(self):
        self.load(cartridge(chr=0))
        self.bank(2,7)
        self.pwrite(0x1000,123)
        self.bank(2,4);self.assertEqual(self.pread(0x1000),0)
        self.bank(3,7);self.assertEqual(self.pread(0x1400),123)
        self.write(0x8000,0x80);self.assertEqual(self.pread(0x400),123)
    def test_mirroring_and_four_screen_override(self):
        self.write(0xA000,0);self.pwrite(0x2000,7)
        self.assertEqual(self.pread(0x2800),7)
        self.write(0xBFFE,1);self.assertEqual(self.pread(0x2400),7)
        self.load(cartridge(flags=8))
        for i in range(4): self.pwrite(0x2000+i*1024,40+i)
        self.write(0xA000,1)
        self.assertEqual([self.pread(0x2000+i*1024) for i in range(4)],[40,41,42,43])
    def test_prg_ram_enable_and_protection(self):
        self.write(0x6000,17);self.assertEqual(self.read(0x6000),17)
        self.write(0xA001,0xC0);self.write(0x6000,99)
        self.assertEqual(self.read(0x6000),17)
        self.write(0xA001,0);self.write(0x6000,55)
        self.assertEqual(self.read(0x6000),0)
        self.write(0xA001,0x80);self.assertEqual(self.read(0x6000),17)
    def test_mapped_reset_nmi_irq_and_level_acknowledge(self):
        v=self.vm.v
        last=v['PRGO']+v['PRGS']-8192
        self.vm.a['ROM'][last+0x1FFA:last+0x2000]=[0,0xE1,0,0xE0,0,0xE2]
        self.vm.a['ROM'][last+0x100]=0x40 # RTI
        self.vm.a['ROM'][last+0x200]=0x40
        self.vm.call('RESETVECTOR');self.assertEqual(v['PC'],0xE000)
        v.update(PC=0xA123,FL=0x21,MIRQ=1,NMI=1)
        self.vm.call('CPU');self.assertEqual((v['PC'],v['CC']),(0xE100,7))
        self.assertEqual(self.vm.a['RAM'][0x1FB],0x21) # B clear
        self.vm.call('CPU');self.assertEqual(v['PC'],0xA123) # NMI wins, RTI restores I=0
        self.vm.call('CPU');self.assertEqual(v['PC'],0xE200)
        self.assertEqual(v['MIRQ'],1) # servicing does not acknowledge level
        self.write(0xE000,0);self.assertEqual(v['MIRQ'],0)
        self.vm.call('CPU');self.assertEqual((v['PC'],v['SP']),(0xA123,253))
        v.update(MIRQ=1,FL=0x24,PC=0xE000)
        self.vm.a['ROM'][last]=0xEA
        self.vm.call('CPU');self.assertEqual(v['PC'],0xE001) # I masks IRQ
    def test_irq_reload_enable_disable_and_a12_filter(self):
        v=self.vm.v
        self.write(0xC000,2);self.write(0xC001,0);self.write(0xE001,0)
        self.edge(0,0);self.edge(8,1)
        self.assertEqual((v['IRQCOUNT'],v['IRQRELOAD']),(2,0))
        self.edge(10,0);self.edge(14,1) # short low pulse ignored
        self.assertEqual(v['IRQCOUNT'],2)
        self.edge(15,1);self.assertEqual(v['IRQCOUNT'],2) # sustained high ignored
        self.edge(20,0);self.edge(28,1);self.assertEqual(v['IRQCOUNT'],1)
        self.write(0xC000,5);self.assertEqual(v['IRQCOUNT'],1) # latch write not immediate
        self.edge(40,0);self.edge(48,1);self.assertEqual((v['IRQCOUNT'],v['MIRQ']),(0,1))
        self.write(0xE000,0);self.assertEqual(v['MIRQ'],0)
        self.edge(60,0);self.edge(68,1);self.assertEqual(v['IRQCOUNT'],5) # counts while disabled
        self.write(0xC000,0);self.write(0xC001,0);self.write(0xE001,0)
        self.assertEqual(v['MIRQ'],0) # enabling alone does not assert
        self.edge(80,0);self.edge(88,1);self.assertEqual(v['MIRQ'],1) # MMC3B/C zero reload
    def test_ppuaddr_can_clock_during_vblank(self):
        v=self.vm.v;v.update(LINE=241,MASK=0,PPUTIME=0)
        self.write(0xC000,0);self.write(0xE001,0)
        self.write(0x2006,0);self.write(0x2006,0)
        v['PPUTIME']=10
        self.write(0x2006,0x10);self.write(0x2006,0)
        self.assertEqual(v['MIRQ'],1)
    def test_fetch_schedule_standard_8x8_and_8x16_dummy_sprites(self):
        v=self.vm.v;v.update(LINE=30,MASK=24,CTRL=8)
        self.write(0xC000,10);self.write(0xC001,0)
        for dot in range(1,341,4):
            v.update(DOT=dot,PPUTIME=dot);self.vm.call('PPUEVENT')
            if dot==257: self.assertEqual(v['IRQCOUNT'],0)
            if dot==261: self.assertEqual(v['IRQCOUNT'],10)
        self.assertEqual(v['IRQCOUNT'],10) # exactly one qualified edge
        # 8x16, both selected tiles low, no real sprites: dummy $FF fetches are high.
        self.vm.a['OAM'][:]=[255]*256
        v.update(LINE=31,MASK=24,CTRL=32)
        for dot in range(1,341,4):
            v.update(DOT=dot,PPUTIME=341+dot);self.vm.call('PPUEVENT')
        self.assertEqual(v['IRQCOUNT'],9)
        # Rendering disabled never clocks from synthetic fetches.
        v.update(LINE=32,MASK=0)
        for dot in range(1,341,4):
            v.update(DOT=dot,PPUTIME=682+dot);self.vm.call('PPUEVENT')
        self.assertEqual(v['IRQCOUNT'],9)
    def test_renderer_reads_selected_chr_rom_for_bg_and_sprites(self):
        v=self.vm.v;v.update(LINE=1,SCANV=4096,CTRL=0,MASK=30)
        self.vm.a['COL']=list(range(64));self.vm.a['OAM'][:]=[255]*256
        # Background tile 0 row 1 in physical bank 10.
        self.bank(0,10)
        base=v['CHRO']+10*1024
        self.vm.a['ROM'][base+1]=0x80;self.vm.a['ROM'][base+9]=0
        self.vm.a['PAL'][1]=2
        self.vm.call('DRAWLINE');self.assertEqual(self.vm.pixels[0,1],2)
        # Sprite tile 1 row 0 in a different bank, bank 12.
        self.vm.a['OAM'][:4]=[0,1,0,0]
        v['CTRL']=8;self.bank(2,12)
        base=v['CHRO']+12*1024
        self.vm.a['ROM'][base+16]=0x80;self.vm.a['ROM'][base+24]=0
        self.vm.a['PAL'][17]=3
        self.vm.call('DRAWLINE');self.assertEqual(self.vm.pixels[0,1],3)
        self.assertTrue(v['STATUS']&64)
    def test_advance_reaches_edges_and_preserves_dma_remainder(self):
        v=self.vm.v;v.update(LINE=261,DOT=0,PPUTIME=0,CYCLES=0,MASK=24,CTRL=8,CC=514)
        self.write(0xC000,3);self.write(0xC001,0)
        self.vm.call('ADVANCE')
        self.assertEqual((v['LINE'],v['DOT'],v['PPUTIME'],v['CYCLES']),(3,178,1542,514))
        self.assertEqual(v['IRQCOUNT'],0) # pre-render and lines 0,1,2 = four clocks
        v.update(LINE=240,DOT=340,CC=1)
        self.vm.call('ADVANCE');self.assertEqual((v['LINE'],v['DOT']),(241,2))
        self.assertTrue(v['STATUS']&128)
    def test_internal_scroll_wrap_and_prerender_reload(self):
        v=self.vm.v
        for start,expected in [(0,0x1000),(0x7000|28*32,29*32),(0x7000|29*32,0x800),(0x7000|31*32,0)]:
            v['PV']=start;self.vm.call('SCROLLNEXT');self.assertEqual(v['PV'],expected)
        # Horizontal bits copied at 257, vertical bits copied in pre-render.
        v.update(LINE=261,DOT=257,MASK=24,CTRL=8,PV=0,PTEMP=0x25A7,PPUTIME=257)
        self.vm.call('PPUEVENT');self.assertEqual(v['PV']&0x41F,0x25A7&0x41F)
        v.update(DOT=281,PPUTIME=281)
        self.vm.call('PPUEVENT');self.assertEqual(v['PV'],0x25A7)
        # The optimized NROM scheduler must visit both reload events too.
        v.update(MAPPER=0,LINE=261,DOT=0,PV=0,PTEMP=0x25A7,CC=100)
        self.vm.call('ADVANCE');self.assertEqual(v['PV'],0x25A7)
        v['MAPPER']=4
        # A scanline captures the live address, allowing PPUADDR raster splits.
        v.update(LINE=31,DOT=1,PV=0x1812,PPUTIME=342)
        self.vm.call('PPUEVENT');self.assertEqual(v['SCANV'],0x1812)
    def test_loader_converter_limits_and_size_parity(self):
        self.load(cartridge(prg=16,chr=16)) # user's ROM dimensions
        maximum=cartridge(prg=32,chr=32,trainer=True)
        validate(maximum);self.assertEqual(len(maximum),MAX_ROM)
        self.load(maximum)
        self.assertEqual(self.vm.a['SRAM'][4096:4608],list(range(256))*2)
        self.assertEqual(decode(encode(maximum)),maximum)
        self.assertLess(len(program(cartridge(prg=16,chr=16))),MAX_PROGRAM_CHARS)
        with self.assertRaisesRegex(ValueError,'character limit'): program(maximum)
        for index,value in [(4,1),(4,3),(4,33),(5,3),(5,33),(8,2),(6,0x20)]:
            bad=bytearray(cartridge());bad[index]=value
            with self.subTest(index=index,value=value):
                with self.assertRaises(ValueError): validate(bad)
                self.vm.a['ROM'][:len(bad)]=bad;self.vm.v['N']=len(bad)
                with self.assertRaises(RuntimeError): self.vm.call('VALIDATE')
    def test_cli_program_embeds_full_rom(self):
        data=cartridge(prg=16,chr=16)
        with tempfile.TemporaryDirectory() as tmp:
            rom=Path(tmp)/'input.nes';output=Path(tmp)/'GAME.bas';rom.write_bytes(data)
            result=subprocess.run([sys.executable,str(ROOT/'tools/rom_to_hex.py'),str(rom),str(output),'--format','program'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            source=output.read_text();embedded=source.split('\n@ROMHEX\n')[1]
            rows=[line[6:-1] for line in embedded.splitlines() if line.startswith('DATA "') and line!='DATA "END"']
            self.assertEqual(bytes.fromhex(''.join(rows)),data)
            self.assertIn('@MAPPERWRITE',source)

if __name__=='__main__': unittest.main()
