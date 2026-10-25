# Pico keyboard transfer

The connected original Pico uses its existing CircuitPython 10.3.1 firmware.
No firmware flash or external Python libraries are required. `boot.py` and
`code.py` retain one-shot arming and stream `/nes.bas` line by line so the
ROM-embedded program does not have to fit in Pico RAM.

The checked-in configuration is disarmed (`armed: false`, `mode: disabled`).
To start a transfer, deliberately edit the Pico's `settings.json` on the device
and set `armed: true` and the desired mode. The full emulator and ROM settings
are:

- `mode: "nes"`, `armed: true`
- 5 ms press, 5 ms release (`key_delay: 0.005`)
- 50 ms pause after each line (`line_delay: 0.05`)
- 30-second startup countdown
- Existing `invert_letter_shift: true` and US HID punctuation mapping

The roughly 909 KB program has a calculated transfer duration of **2.8 hours
before USB/editor overhead**. The new timing has not been tested in the Switch
editor; it is a trial rate, not a verified maximum speed.

1. Open an empty program slot in SmileBASIC **EDIT**, cursor at the beginning,
   using the same US keyboard/case settings as your previous sender test.
   Turn editor wrapping off. Do not receive the program in DIRECT mode.
2. Eject and unplug the Pico from the PC, then connect it to the Switch dock.
3. The LED blinks during the 30-second countdown. It then types the program.
   Unplugging stops the transfer. The sender does not press Run or save.
4. The LED stays on when finished; rapid blinking indicates an error. Progress
   is written to `status.json` every 128 lines. This is not a resume mechanism.
5. The arming flag is consumed before typing begins. The next boot returns to
   maintenance mode, exposing storage and serial without sending keys.

For a short speed check first, copy `settings-speed-test.json` to the Pico as
`settings.json`, then set `armed: true` on the Pico before disconnecting it. The next connection types
`editor-test.bas` at the same fast rate instead of the full program. Confirm
that every source character arrived. Manually running the short test should
print the case check, punctuation character codes, two indentation messages,
and `PICO TEST DONE`.

After the short test, reconnect to the PC and edit the Pico's settings to arm
the full NES transfer. If fast typing drops
characters, try `key_delay: 0.01` or `0.02` before a full transfer.

The one-shot request applies to whichever USB host the Pico next connects to.
To disable it before reconnecting, set `armed: false` and `mode: "disabled"` in
the Pico's `settings.json`. File edits do not reboot the sender automatically.

Original device files were backed up locally under `pico/backups/` before any
changes. `pico/deployment.json` records installed file sizes and SHA-256 hashes.
The on-device `nes.bas` is an exact copy of the local, ROM-embedded `GAME.bas`;
the unrelated existing `bootstrap.bas` is retained on the device.
