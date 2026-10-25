"""One-shot US HID keyboard sender. NES source is streamed, never read at once.

An inactive session never sends keys. Arming is consumed by boot.py once.
"""
import json
import time
import board
import digitalio
import os
import supervisor
import usb_hid

supervisor.runtime.autoreload = False
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT


def idle():
    while True:
        time.sleep(1)


def status(state, **details):
    with open('/status.json', 'w') as target:
        json.dump(dict(state=state, **details), target)
    os.sync()


def source_lines(mode):
    if mode == 'test':
        yield 'PRINT "NS2DISTCHECK1234 ABCabc"'
        return
    filenames = {'editor_test': '/editor-test.bas',
                 'bootstrap': '/bootstrap.bas', 'nes': '/nes.bas'}
    with open(filenames[mode], 'r') as source:
        for line in source:
            # Preserve indentation and trailing spaces, removing only the newline.
            yield line.rstrip('\r\n')


def keymap(invert):
    mapping = {}
    for i in range(26):
        mapping[chr(97+i)] = (2 if invert else 0, 4+i)
        mapping[chr(65+i)] = (0 if invert else 2, 4+i)
    for i, char in enumerate('1234567890'):
        mapping[char] = (0, 30+i)
    for plain, shifted, usage in (
        ('-', '_', 45), ('=', '+', 46), ('[', '{', 47),
        (']', '}', 48), ('\\', '|', 49), (';', ':', 51),
        ("'", '"', 52), ('`', '~', 53), (',', '<', 54),
        ('.', '>', 55), ('/', '?', 56),
    ):
        mapping[plain] = (0, usage)
        mapping[shifted] = (2, usage)
    for char, number in zip('!@#$%^&*()', '1234567890'):
        mapping[char] = (2, mapping[number][1])
    mapping[' '] = (0, 44)
    return mapping


def main():
    with open('/settings.json') as source:
        config = json.load(source)
    mode = config.get('mode', 'disabled')
    if mode == 'disabled':
        print('Sender disabled. No keys will be sent.')
        return
    with open('/session.json') as source:
        active = json.load(source).get('active') is True
    if not active:
        print('Maintenance boot. No keys will be sent.')
        return
    if mode not in ('test', 'editor_test', 'bootstrap', 'nes'):
        raise ValueError('Invalid mode')
    editor_mode = mode != 'test'
    invert = bool(config.get('invert_letter_shift', False))
    mapping = keymap(invert)
    characters = total_lines = 0
    # Validate the entire source before sending any keys. Memory stays bounded
    # by the longest line, even for a ROM-embedded program larger than Pico RAM.
    for line in source_lines(mode):
        total_lines += 1
        characters += len(line)
        for char in line:
            if char not in mapping:
                raise ValueError('Unsupported character: ' + repr(char))
    if not total_lines:
        raise ValueError('Empty source')
    keyboard = next(d for d in usb_hid.devices
                    if d.usage_page == 1 and d.usage == 6)
    delay = float(config.get('key_delay', 0.05))
    line_delay = float(config.get('line_delay', 0.3))
    if delay < 0.001 or line_delay < 0:
        raise ValueError('Invalid timing: key_delay >= 0.001, line_delay >= 0')

    def key(modifier, usage):
        try:
            keyboard.send_report(bytes((modifier, 0, usage, 0, 0, 0, 0, 0)))
            time.sleep(delay)
        finally:
            keyboard.send_report(bytes(8))
        time.sleep(delay)

    status('countdown', mode=mode, characters=characters, total_lines=total_lines)
    print('Armed:', mode, 'lines:', total_lines, 'characters:', characters)
    # Unplugging cancels this one-shot run; a later boot restores maintenance.
    for _ in range(max(10, int(config.get('start_delay', 30)))):
        led.value = True
        time.sleep(0.2)
        led.value = False
        time.sleep(0.8)
    sent = 0
    try:
        keyboard.send_report(bytes(8))
        status('sending', mode=mode, total_lines=total_lines, completed_lines=0,
               boot_protocol=usb_hid.get_boot_device())
        for line in source_lines(mode):
            if editor_mode:
                key(0, 74)  # Home: select inherited indentation on the new line.
                key(2, 77)  # Shift+End: the first character replaces the selection.
            for char in line:
                key(*mapping[char])
            if editor_mode:
                key(0, 40)  # Enter in EDIT mode only; never execute in DIRECT.
                time.sleep(line_delay)
            sent += 1
            if sent % 128 == 0:
                led.value = not led.value
                status('sending', mode=mode, total_lines=total_lines,
                       completed_lines=sent, boot_protocol=usb_hid.get_boot_device())
    finally:
        keyboard.send_report(bytes(8))
    led.value = True
    status('finished', mode=mode, characters=characters, total_lines=total_lines,
           completed_lines=sent, boot_protocol=usb_hid.get_boot_device(),
           invert_letter_shift=invert, key_delay=delay)
    print('Finished. No Run or save commands were sent.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Sender error:', repr(error))
        try:
            status('error', message=repr(error))
        except Exception as log_error:
            print('Could not save error:', repr(log_error))
        while True:
            led.value = not led.value
            time.sleep(0.1)
    idle()
