"""Consume one file-based arming request; next boot restores maintenance USB."""
import json
import os
import storage
import usb_cdc
import usb_hid
import usb_midi

try:
    with open('/status.json') as source:
        print('Previous sender:', source.read())
except OSError:
    print('No previous file-based status.')
with open('/settings.json') as source:
    config = json.load(source)
armed = (config.get('armed') is True
         and config.get('mode') in ('test', 'editor_test', 'bootstrap', 'nes'))
# boot.py runs before the USB drive is exposed. Temporarily own the filesystem
# to consume the arming request and record which mode this boot should use.
storage.remount('/', readonly=False)
if armed:
    config['armed'] = False
    with open('/settings.json', 'w') as target:
        json.dump(config, target)
with open('/session.json', 'w') as target:
    json.dump({'active': armed}, target)
os.sync()
if armed:
    storage.disable_usb_drive()
    usb_cdc.disable()
    usb_midi.disable()
    usb_hid.enable((usb_hid.Device.KEYBOARD,), boot_device=1)
    print('One-shot keyboard-only USB mode.')
else:
    storage.remount('/', readonly=True)
    usb_hid.disable()
    usb_midi.disable()
    print('Maintenance mode. Storage and serial available; typing disabled.')
