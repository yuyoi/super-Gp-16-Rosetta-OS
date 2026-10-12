#!/usr/bin/env python3
"""One-shot build: your own GP-16 IC11 dump -> burn files in build/.
Usage: py -3.11 build_all.py <your_ic11_dump.bin>
Copies the dump to ../dumps/gp16_u1_ic11.bin (gen_pedal_data.py and the emulator tests read it there), generates
pedal_data.inc, assembles the boot dragon and the pedal menu with NASM, then runs build_mod.py.
NASM: on PATH, in ../tools/nasm-2.16.03/, or named by the NASM environment variable."""
import hashlib, os, shutil, subprocess, sys

VERSION = '2.2'                     # pedal_menu.asm is the v1 source; older menus: pedal_menu_v07/v08/v09.asm
STOCK_MD5 = 'ac5f56bcb3d8c30ddf3f1ffe88b13556'
here = os.path.dirname(os.path.abspath(__file__))


def nasm():
    for p in (os.environ.get('NASM'), os.path.join(here, '..', 'tools', 'nasm-2.16.03', 'nasm.exe'),
              shutil.which('nasm')):
        if p and os.path.exists(p):
            return p
    sys.exit('NASM not found: put nasm on PATH, in ../tools/nasm-2.16.03/, or set NASM=<path to nasm>')


def run(*a):
    print('>', ' '.join(a))
    subprocess.run(a, cwd=here, check=True)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    md5 = hashlib.md5(open(src, 'rb').read()).hexdigest()
    if md5 != STOCK_MD5:
        sys.exit(f'{src}: md5 {md5} is not the known GP-16 "Super GP Ver 1.0" IC11 dump ({STOCK_MD5}), refusing')
    dst = os.path.join(here, '..', 'dumps', 'gp16_u1_ic11.bin')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    n = nasm()
    run(sys.executable, 'gen_pedal_data.py')
    run(n, '-f', 'bin', 'dragon_boot.asm', '-o', 'dragon_boot.bin')
    run(n, '-f', 'bin', 'pedal_menu.asm', '-o', 'pedal_menu.bin', '-l', 'pedal_menu.lst')
    run(sys.executable, 'build_mod.py', dst, 'build', VERSION)
    print(f'\nburn build/gp16_mod_v{VERSION.replace(".", "_")}_sst512k.bin (SST39SF040 / A29040), read back, compare.')


if __name__ == '__main__':
    main()
