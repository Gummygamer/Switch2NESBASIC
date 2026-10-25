"""Exercise the generated BASIC APU through its CPU bus interface."""
import unittest
from pathlib import Path
from basic_vm import BasicVM

class APUTests(unittest.TestCase):
    def setUp(self):
        self.vm=BasicVM((Path(__file__).resolve().parents[1]/'NES.bas').read_text())
        self.vm.a['APLTABLE'][:]=[10,254,20,2,40,4,80,6,160,8,60,10,14,12,26,14,12,16,24,18,48,20,96,22,192,24,72,26,16,28,32,30]
    def write(self,addr,value):
        self.vm.v.update(AD=addr,WV=value);self.vm.call('WRITE')
    def status(self):
        self.vm.v['AD']=0x4015;self.vm.call('READ');return self.vm.v['RV']
    def advance(self,cycles):
        self.vm.v['CC']=cycles;self.vm.call('APADVANCE')
    def test_enable_length_and_status_irq_ack(self):
        self.write(0x4003,0);self.assertEqual(self.status(),0)
        self.write(0x4015,15)
        for addr in (0x4003,0x4007,0x400b,0x400f): self.write(addr,0)
        self.vm.v['APIRQ']=1
        self.assertEqual(self.status(),79);self.assertEqual(self.status(),15)
        self.write(0x4015,0);self.assertEqual(self.status(),0)
    def test_frame_irq_and_inhibit(self):
        self.advance(29826);self.assertEqual(self.status(),64)
        self.write(0x4017,64);self.advance(29826)
        self.assertEqual(self.status(),0)
    def test_five_step_immediate_clocks_no_irq(self):
        self.write(0x4015,1);self.write(0x4003,0)
        self.write(0x4017,128)
        self.assertEqual(self.vm.a['APLEN'][0],9)
        self.advance(37283);self.assertEqual(self.status(),1)
    def test_envelope_and_triangle_linear_reload(self):
        self.write(0x4000,0);self.write(0x4003,0)
        self.vm.call('APQUARTER');self.assertEqual(self.vm.a['APENV'][0],15)
        self.vm.call('APQUARTER');self.assertEqual(self.vm.a['APENV'][0],14)
        self.write(0x4008,3);self.write(0x400b,0)
        self.vm.call('APQUARTER');self.assertEqual(self.vm.v['APLINEAR'],3)
        self.vm.call('APQUARTER');self.assertEqual(self.vm.v['APLINEAR'],2)
    def test_pulse_negate_channel_difference(self):
        for api in (0,1):
            self.write(0x4002+api*4,100);self.write(0x4001+api*4,0x89)
            self.vm.v['API']=api;self.vm.call('APTARGET')
            self.assertEqual(self.vm.v['APTARGET'],49+api)
