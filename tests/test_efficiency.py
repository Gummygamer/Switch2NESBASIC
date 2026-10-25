"""Regression coverage for optimized fetches and background tile spans."""
import random
import unittest
from pathlib import Path
from basic_vm import BasicVM

ROOT = Path(__file__).resolve().parents[1]

class EfficiencyTests(unittest.TestCase):
    def test_background_against_pixel_reference(self):
        rng = random.Random(6502)
        vm = BasicVM((ROOT/'NES.bas').read_text())
        for name, size, limit in [('CHR',8192,256),('NT',4096,256),('PAL',32,64)]:
            vm.a[name][:] = [rng.randrange(limit) for _ in range(size)]
        vm.a['COL'][:] = list(range(64))
        vm.a['CHRBANK'][:] = [i*1024 for i in range(8)]
        for fine in range(8):
            for mirror in range(2):
                for left in range(2):
                    scan = rng.randrange(32768)
                    mask = 8 + left*2 + rng.randrange(2)
                    ctrl = rng.randrange(256)
                    vm.v.update(SCANV=scan,FINE=fine,MIRROR=mirror,FOUR=0,
                                MASK=mask,CTRL=ctrl,CHRS=0,LINE=10)
                    expected = []
                    for x in range(256):
                        color = vm.a['PAL'][0]
                        if x>=8 or left:
                            wx = x+fine+8*(scan&31)
                            nx = ((scan>>10)&1)^((wx//256)&1)
                            ny = (scan>>11)&1
                            tx,ty = (wx%256)//8,(scan>>5)&31
                            pn = (nx+2*ny)&1 if mirror else (nx+2*ny)>>1
                            base = pn*1024
                            tile = vm.a['NT'][base+ty*32+tx]
                            attr = vm.a['NT'][base+960+(ty//4)*8+tx//4]
                            attr = (attr>>(2*((tx//2)%2)+4*((ty//2)%2)))&3
                            ca = (4096 if ctrl&16 else 0)+tile*16+((scan>>12)&7)
                            bit = 7-(wx&7)
                            pixel = ((vm.a['CHR'][ca]>>bit)&1)+2*((vm.a['CHR'][ca+8]>>bit)&1)
                            if pixel: color = vm.a['PAL'][attr*4+pixel]
                        expected.append(color&48 if mask&1 else color)
                    vm.call('DRAWLINE')
                    self.assertEqual([vm.pixels[x,10] for x in range(256)], expected)

    def test_fetch_matches_bus_at_bank_and_address_boundaries(self):
        vm = BasicVM((ROOT/'NES.bas').read_text())
        vm.v.update(PRGO=16,PRGS=32768,RAMCTRL=128)
        vm.a['PRGBANK'][:] = [24576,8192,0,16384]
        for name in ['ROM','RAM','SRAM']:
            vm.a[name][:] = [(i*37+11)&255 for i in range(len(vm.a[name]))]
        for mapper in [0,4]:
            vm.v['MAPPER']=mapper
            for address in [0,2047,2048,8191,0x6000,0x7fff,0x8000,0x9fff,0xa000,0xbfff,0xc000,0xdfff,0xe000,0xffff]:
                vm.v['AD']=address
                vm.call('READ')
                expected=vm.v['RV']
                vm.v['PC']=address
                vm.call('FETCH')
                self.assertEqual(vm.v['RV'],expected)
                self.assertEqual(vm.v['PC'],(address+1)&65535)

    def test_sparse_timing_matches_full_fetch_schedule(self):
        source = (ROOT/'NES.bas').read_text()
        fast = 'IF MAPPER==4 AND (MASK AND 24)!=0 AND ((DOT>=257 AND DOT<321) OR (CTRL AND 16)!=0 OR A12HIGH) THEN'
        self.assertIn(fast,source)
        sparse = BasicVM(source)
        full = BasicVM(source.replace(fast,'IF MAPPER==4 AND (MASK AND 24)!=0 THEN'))
        rng = random.Random(341)
        for vm in [sparse,full]:
            vm.v.update(MAPPER=4,MASK=24,LINE=261,IRQENABLE=1,IRQLATCH=7,A12LOW=-8)
            vm.a['SPR12'][:] = [4096,0]*4
        for step in range(180):
            cc = rng.choice([2,3,7,514])
            if step%17==0:
                ctrl = rng.choice([0,8,16,32,56])
                for vm in [sparse,full]: vm.v['CTRL']=ctrl
            for vm in [sparse,full]:
                vm.v['CC']=cc
                vm.call('ADVANCE')
            for key in ['DOT','LINE','PPUTIME','IRQCOUNT','IRQRELOAD','MIRQ',
                        'A12HIGH','A12LOW','PV','STATUS','FRAMEPEND','SCANV']:
                self.assertEqual(sparse.v[key],full.v[key],(step,key))
