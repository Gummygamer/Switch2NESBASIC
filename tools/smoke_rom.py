#!/usr/bin/env python3
"""Run a ROM through the host BASIC evaluator; this is not a console test."""
import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from basic_vm import BasicVM
from build import table,OPS,MODES
from rom_to_hex import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom',type=Path)
    parser.add_argument('--frames',type=int,default=10)
    args=parser.parse_args()
    if args.frames<1: parser.error('--frames must be positive')
    data=args.rom.read_bytes();validate(data)
    vm=BasicVM((ROOT/'NES.bas').read_text());vm.a['ROM'][:len(data)]=data
    vm.v.update(N=len(data),SP=253,FL=36,LINE=261)
    vm.call('VALIDATE');vm.call('CARTINIT');vm.call('RESETVECTOR')
    for op,(name,mode,cycles,penalty) in table().items():
        for arr,value in [('OT',OPS.index(name)+1),('MT',MODES.index(mode)),('CT',cycles),('PT',penalty)]:
            vm.a[arr][op]=value
    vm.a['COL']=list(range(64))
    frames=instructions=nmis=irqs=0
    print(f"Mapper {vm.v['MAPPER']}; reset PC ${vm.v['PC']:04X}",flush=True)
    try:
        while frames<args.frames:
            if vm.v['NMI']: nmis+=1
            elif vm.v['MIRQ'] and not vm.v['FL']&4: irqs+=1
            vm.call('CPU');vm.call('ADVANCE');instructions+=1
            if vm.v['FRAMEPEND']:
                frames+=1;vm.v['FRAMEPEND']=0
                if frames%5==0 or frames==args.frames:
                    print(f"Frame {frames}: PC=${vm.v['PC']:04X}, mask=${vm.v['MASK']:02X}, NMI={nmis}, IRQ={irqs}, palette colors={len(set(vm.pixels.values()))}",flush=True)
    except Exception:
        print(f"Stopped after {instructions} instructions at PC=${vm.v['PC']:04X}",file=sys.stderr)
        raise
    print(f'Completed {instructions} CPU steps. Host logic only; no controller input.',flush=True)

if __name__=='__main__':
    main()
