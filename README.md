# Switch2NESBASIC

An experimental NES emulator written in SmileBASIC 4, targeting the Japanese
4.4.6 demo on Switch 2. **It has not been run on that device or in the real
SmileBASIC interpreter.** It is an NROM/MMC3 prototype with approximate four-channel sound; game compatibility
and real-time speed are not established.

`NES.bas` is the generated, self-contained program. It includes an original
16 KiB test ROM encoded as hexadecimal DATA strings. No game ROM is needed
for the first test. Enter the source in the SmileBASIC editor and run it. The
expected result is a 256×240 field of alternating pixels whose color changes
once per emulated frame. The image uses the top-left part of the default
400×240 screen. The console's + button stops execution.

The files in this repository are PC text files, not native Switch project
files. This project does not provide a PC-to-Switch transfer mechanism. Use
whatever editor-entry method is available to you. Do not assume that the demo
can import local PC files or save edited programs. The embedded DATA route
requires neither a ROM file load nor a save operation while the emulator runs.

## Use your ROM as hex text

The input is the **entire iNES file, including its 16-byte header**, encoded as
two hex digits per byte. It must begin `4E45531A`. The loader accepts upper- or
lowercase hex and ASCII spaces, tabs, CR and LF. It rejects `0x` prefixes,
addresses, separators, comments, invalid digits and incomplete bytes.

Generate a complete program with a different embedded ROM:

```sh
python3 tools/rom_to_hex.py game.nes GAME.bas --format program
```

Enter `GAME.bas` in place of `NES.bas`. This replaces the default test ROM;
it does not add a second ROM. The converter requires Python 3 and has no
third-party dependencies. The generated source is checked against SmileBASIC's
1,048,576-character program limit. Larger cartridges may require TXT loading,
even when the mapper can address their full ROM.

To generate only replacement DATA lines:

```sh
python3 tools/rom_to_hex.py game.nes ROMDATA.bas --format data
```

Replace `@ROMHEX` and everything below it with that output. Keep
`ROMFILE$=""` at the beginning of the program. A block has this form:

```basic
@ROMHEX
DATA "4E45531A..."
DATA "..."
DATA "END"
```

The ellipses above illustrate omitted bytes; they are not valid input.

For an environment where a TXT file is already available inside the
SmileBASIC project:

```sh
python3 tools/rom_to_hex.py game.nes ROMHEX.txt
```

Set `ROMFILE$="TXT:ROMHEX"`. This selects `LOADV` instead of embedded DATA.
Creating `ROMHEX.txt` on a PC does not put it in the Switch project. If file
loading is unavailable in your demo session, use the embedded route.

## Supported hardware

- All 151 documented 6502 opcode encodings, binary NES ADC/SBC, status flags,
  stack, BRK/RTI, NMI, branches and indexed-read page penalties. The indirect
  JMP page-wrap behavior is included. Unofficial opcodes stop with a diagnostic.
- iNES mapper 0: 16/32 KiB PRG, 8 KiB CHR ROM or CHR RAM.
- iNES mapper 4 (standard MMC3): power-of-two 32–512 KiB PRG, power-of-two
  8–256 KiB CHR ROM or 8 KiB CHR RAM; both PRG banking modes, CHR inversion,
  paired 2 KiB and individual 1 KiB banks, dynamic mirroring, PRG RAM protection,
  and MMC3B/C-style IRQ latch/reload/enable/acknowledge. Reset, NMI and IRQ vectors
  all read through the active PRG map. Rendering and PPUDATA use the CHR map.
- Trainer initialization, 2 KiB mirrored CPU RAM and volatile 8 KiB cartridge RAM.
  Other mappers, NES 2.0, PAL-marked headers, VS/PlayChoice, oversized PRG RAM,
  unsupported bank sizes and unexpected file lengths are rejected.
- Horizontal, vertical and four-screen nametable mapping, palette mirrors,
  buffered PPUDATA reads, shared PPU address/scroll write latch and OAM DMA.
- Background tiles, attributes, internal v/t scrolling with scanline address
  snapshots and coarse/fine Y wrap, 8×8 and 8×16 sprites,
  flips, priority, left-edge masks, grayscale, approximate sprite-zero hit and
  a simple eight-sprites-per-line limit.
- One serial controller; reads after its eighth bit return 1. Controller 2 is
  disconnected.

| Switch control (standard full controller) | NES control |
| --- | --- |
| A | A |
| B | B |
| L | Select |
| R | Start |
| D-pad | D-pad |

Controller input is sampled once per emulated frame using SmileBASIC 4's
`BUTTON(ControllerID,ButtonID)` API, not the older SmileBASIC 3 bitmask API.

## Known limits

Pulse (including duty and sweep), triangle and noise register writes now drive
looping SmileBASIC waveforms. Length counters, envelopes, the triangle linear
counter, `$4015` status/enables and an approximate NTSC frame sequencer/IRQ
advance with CPU cycles, including OAM DMA stalls. Reading `$4015` clears the
frame IRQ; `$4017` controls its inhibition and four/five-step mode.

Audio pitch and volume are updated once per emulated frame using `WAVSETA`,
`BEEP`, `BEEPPIT` and `BEEPVOL`. This is approximate synthesis: short sounds
between updates can be lost, oscillator phase is not emulated, noise uses a
short looping approximation (its mode bit is ignored), and mixing is linear.
Frame-counter reset delay and IRQ edge races, precise sweep reload timing,
DMC samples/DMA/IRQs and expansion audio are unsupported. The bundled visual
diagnostic does not program the APU and remains silent. Cartridge RAM is not saved.
Sound API behavior and playback still need testing on SmileBASIC 4.4.6; the
online sound reference currently describes 4.4.9.

MMC3 support targets standard boards with MMC3B/C zero-counter IRQ behavior.
It does not implement MMC6 PRG RAM, MMC3A/NEC counter differences, the `$C001`
reload glitch or extended mapper variants such as 118/119. An iNES mapper-4
header alone cannot distinguish MMC6 boards, so acceptance of a header does
not establish support for that cartridge's precise hardware.

PPU timing advances between CPU instructions, including DMA stall time. During
rendering, simulated nametable/pattern fetch phases drive the MMC3 A12 filter,
with sprite bank bits selected from the next scanline's first eight sprites and
high-bank dummy fetches for unused 8×16 slots. Repeated short low pulses are
filtered. The counter keeps running while IRQ delivery is disabled, and pending
IRQs remain asserted until acknowledged through `$E000`. Outside rendering,
CPU PPUADDR/PPUDATA accesses can also drive A12. Raster timing is approximate;
inverted background/sprite table arrangements, CPU/PPU clock alignment, rendering
races and odd-frame effects may count differently from hardware.

The image is still rendered from a scanline snapshot rather than a pixel-fetch
pipeline. The internal scroll address is captured at the line start; vertical
increment and horizontal reload occur at dot 257, and pre-render vertical reload
at dot 281. This supports scanline PPUADDR/scroll changes but approximates their
exact timing. Rendering-time PPUDATA increments and midline scroll changes are
not hardware accurate. Sprite-zero hit is set at the end of the visible line,
overflow uses a simple count, and the pre-render sprite evaluation is simplified.
Color emphasis, open-bus details, read/modify/write dummy bus accesses,
interrupt polling delays/races, odd-frame dot skipping and reset warm-up behavior
are not accurate. Headers with no PAL flag are treated as NTSC.

Games may still fail or show timing/scrolling errors. A frame runs for 262×341
approximate PPU dots at three dots per CPU cycle, then waits for one host VSYNC.
There is no catch-up scheduler or performance claim. BASIC pixel composition, CPU execution and simulated fetch events may still be slow.
The renderer caches scanline scroll/pattern values, reads mapped nametable data
directly once per tile span, and uploads each completed
scanline with indexed `GLOAD` (240 graphics calls per frame). CPU and addressing
mode dispatch use balanced branches, and instruction fetches have direct ROM/RAM
paths. MMC3 timing skips redundant low-A12 background fetch events while retaining
sprite fetch events and scroll/status boundaries. These optimizations have host
regression coverage, but their speed and graphics behavior still need console testing.

## Development and verification

Edit `src/core.bas` and the opcode specification in `tools/build.py`, then:

```sh
python3 tools/make_diagnostic.py
python3 tools/build.py
python3 -m unittest discover -s tests -v
```

`build.py` always embeds the original diagnostic. Run the converter again to
create a program containing your own ROM after rebuilding.

The host tests execute the generated BASIC CPU, bus and renderer routines
through a small numeric-subset evaluator. They cover 2,000 seeded ADC/SBC
cases, execution of every official opcode, indexed addressing and branch
penalties, JMP wrap, stack/NMI return, DMA wrap and stall, controller reads,
PPU mirroring/read buffering, sprite priority/flipping/zero hit, ROM validation,
converter round trips and the diagnostic's boot/render/NMI behavior. Mapper
regressions also cover both PRG/CHR modes, register aliases, ROM/RAM banks,
mirroring overrides, RAM protection, mapped vectors and interrupt priority,
IRQ filtering/reload/acknowledge, manual PPUADDR clocks, dummy sprite fetches,
DMA timing across scanlines, scrolling reload/wrap, and a complete converter
CLI round trip for a 256 KiB PRG / 128 KiB CHR cartridge.

For an optional local ROM smoke run through the same evaluator:

```sh
python3 tools/smoke_rom.py game.nes --frames 30
```

This executes the actual generated CPU, bus, timing and renderer routines with
no controller input. It reports progress and interrupts; it does not certify
gameplay or console performance.

This evaluator tests logic under its own expression semantics. It does not
validate SmileBASIC syntax, graphical API signatures, controller setup, demo
restrictions or speed. This has not passed nestest or a full NES conformance
suite. The required next acceptance test is to run the bundled diagnostic in
SmileBASIC 4.4.6 on the target console.

## References

- [SmileBASIC 4 sound API](https://sup4.smilebasic.com/en/doku.php?id=reference%3ASound)
- [NESdev APU reference](https://www.nesdev.org/wiki/APU)

- [Official SmileBASIC 4 specifications](https://www.petc4.smilebasic.com/basicspecification?lang=en)
- [Official SmileBASIC 4 file reference (LOADV)](https://sup4.smilebasic.com/en/doku.php?id=reference%3Afiles)
- [Official SmileBASIC 4 controller reference](https://sup4.smilebasic.com/en/doku.php?id=reference%3AVarious_Inputs)
- [NESdev PPU programmer reference](https://www.nesdev.org/wiki/PPU_programmer_reference)
- [NESdev MMC3 register and IRQ reference](https://www.nesdev.org/wiki/MMC3)
- [NESdev unofficial opcode reference](https://www.nesdev.org/wiki/CPU_unofficial_opcodes)

The diagnostic ROM and emulator code are original project code. The distributed diagnostic contains no commercial ROM data. User-generated
`GAME.bas` embeds the supplied ROM and should stay local.
