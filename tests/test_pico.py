"""Host checks for the Pico sender; no USB reports are sent to real hardware."""
import importlib.util
import io
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

class PicoTests(unittest.TestCase):
    def setUp(self):
        self.reports=[]
        keyboard=types.SimpleNamespace(usage_page=1,usage=6,send_report=self.reports.append)
        self.modules={
            'board':types.SimpleNamespace(LED=object()),
            'digitalio':types.SimpleNamespace(DigitalInOut=lambda pin:types.SimpleNamespace(value=False),Direction=types.SimpleNamespace(OUTPUT=1)),
            'supervisor':types.SimpleNamespace(runtime=types.SimpleNamespace(autoreload=True)),
            'usb_hid':types.SimpleNamespace(devices=[keyboard],get_boot_device=lambda:1),
        }
        spec=importlib.util.spec_from_file_location('pico_sender',ROOT/'pico/code.py')
        self.sender=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,self.modules):spec.loader.exec_module(self.sender)
    def test_fast_timing_and_editor_reports(self):
        config=json.loads((ROOT/'pico/settings.json').read_text())
        self.assertEqual(config['key_delay'],0.005)
        config['mode']='nes'  # Exercise sending independently of the local arming setting.
        sleeps=[];states=[]
        files={'/settings.json':json.dumps(config),'/session.json':'{"active":true}','/nes.bas':'PRINT "A#"\n  AA\n'}
        def fake_open(name,*args,**kwargs): return io.StringIO(files[name])
        with patch.object(self.sender,'open',fake_open,create=True),patch.object(self.sender.time,'sleep',sleeps.append),patch.object(self.sender,'status',lambda state,**kw:states.append((state,kw))):
            self.sender.main()
        self.assertEqual(states[-1][0],'finished')
        self.assertEqual(states[-1][1]['completed_lines'],2)
        # Home, Shift+End, source characters, Enter; every key has a release.
        self.assertEqual(self.reports[1],bytes((0,0,74,0,0,0,0,0)))
        self.assertEqual(self.reports[3],bytes((2,0,77,0,0,0,0,0)))
        presses=[r for r in self.reports if r[2]]
        self.assertEqual(sum(r[2]==40 for r in presses),2)
        self.assertEqual(self.reports[-1],bytes(8))
        self.assertIn(0.005,sleeps);self.assertNotIn(0.05,sleeps[:60])
    def test_inactive_session_never_types(self):
        files={'/settings.json':'{"mode":"nes"}','/session.json':'{"active":false}'}
        with patch.object(self.sender,'open',lambda name,*a,**kw:io.StringIO(files[name]),create=True):
            self.sender.main()
        self.assertEqual(self.reports,[])
    def test_full_payload_streams_without_reading_into_ram(self):
        class StreamingOnly:
            def __init__(self): self.f=io.StringIO((ROOT/'NES.bas').read_text()*16)
            def __enter__(self):return self
            def __exit__(self,*args):self.f.close()
            def __iter__(self):return iter(self.f)
            def read(self,*a):raise AssertionError('payload must be streamed')
        mapping=self.sender.keymap(True)
        count=chars=0
        with patch.object(self.sender,'open',lambda *a,**kw:StreamingOnly(),create=True):
            for line in self.sender.source_lines('nes'):
                self.assertLess(len(line),1024)
                self.assertTrue(all(c in mapping for c in line))
                count+=1;chars+=len(line)
        expected=(ROOT/'NES.bas').read_text().splitlines()*16
        self.assertEqual(chars,sum(map(len,expected)))
        self.assertEqual(count,len(expected))
    def test_boot_consumes_arming_once(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'settings.json').write_text('{"mode":"nes","armed":true}')
            actions=[]
            modules={
                'os':types.SimpleNamespace(sync=lambda:None),
                'storage':types.SimpleNamespace(remount=lambda *a,**kw:actions.append(('mount',kw)),disable_usb_drive=lambda:actions.append('no_disk')),
                'usb_cdc':types.SimpleNamespace(disable=lambda:actions.append('no_serial')),
                'usb_midi':types.SimpleNamespace(disable=lambda:None),
                'usb_hid':types.SimpleNamespace(Device=types.SimpleNamespace(KEYBOARD=1),enable=lambda *a,**kw:actions.append('keyboard'),disable=lambda:actions.append('no_keyboard')),
            }
            def local_open(name,*a,**kw):return (root/Path(name).name).open(*a,**kw)
            boot=compile((ROOT/'pico/boot.py').read_text(),'boot.py','exec')
            with patch.dict(sys.modules,modules):
                exec(boot,{'open':local_open})
                self.assertFalse(json.loads((root/'settings.json').read_text())['armed'])
                self.assertTrue(json.loads((root/'session.json').read_text())['active'])
                self.assertIn('keyboard',actions)
                actions.clear();exec(boot,{'open':local_open})
                self.assertFalse(json.loads((root/'session.json').read_text())['active'])
                self.assertNotIn('keyboard',actions)
                self.assertIn('no_keyboard',actions)

if __name__=='__main__':unittest.main()
