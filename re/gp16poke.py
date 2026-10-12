#!/usr/bin/env python3
"""PC side of the GP-16 DSP backdoor (ROM mod v0.2+). Needs mido + python-rtmidi (installed for py -3.10).
Wiring: PC MIDI OUT -> GP-16 MIDI IN, GP-16 MIDI OUT -> PC MIDI IN (OCTA-CAPTURE). GP-16 on MIDI channel 1.

  py -3.10 gp16poke.py ping
  py -3.10 gp16poke.py write <chip> <step> <instr24> <coef16> [commit]   (hex numbers; commit default 8)
  py -3.10 gp16poke.py restore <chip> <step>          rewrite the stock instruction from the ROM image (commit 0)
  py -3.10 gp16poke.py raww <offset> <byte>            raw write 8000:offset
  py -3.10 gp16poke.py rawr <offset>                   raw read 8000:offset
  py -3.10 gp16poke.py mr <seg> <off> [n]              read n bytes (default 8) at seg:off  (v3 ROM)
  py -3.10 gp16poke.py mw <seg> <off> <byte>           write one byte to seg:off            (v3 ROM)
  py -3.10 gp16poke.py keys                            poll the panel key bytes (hold a button to map it)
  py -3.10 gp16poke.py jack <0|1|2|3>                  route output: 0=CH1 1=CH2 2=CH1&2 3=mute test
  py -3.10 gp16poke.py show <chip> <from> <to>         print stock instructions from the ROM image
Common seg:off -- RAM FA00:A310/A311 key strobes, FA00:9D06 edit buffer; latch 6000:1 chan 6000:6 relay; LCD 2000:0 cmd 2000:1 data.
Options: --port NAME (substring, default OCTA-CAPTURE)
"""
import sys, os, time, argparse

ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dumps', 'gp16_u1_ic11.bin')
IMG = {0: 0x1A750, 1: 0x1ADC8, 2: 0x1B4C4}       # boot program images, 3 bytes/step, low byte first


def stock_instr(chip, step):
    d = open(ROM, 'rb').read(); o = IMG[chip] + 3 * step
    return d[o] | d[o + 1] << 8 | d[o + 2] << 16


def nib(v, n):
    return [(v >> (4 * i)) & 0xF for i in reversed(range(n))]


def msg_write(chip, step, instr, coef, commit):
    return [0x47, 1, chip & 3] + nib(step, 3) + nib(instr, 6) + nib(coef, 4) + nib(commit, 2)


def msg_peek(seg, off, n):
    return [0x47, 5] + nib(seg, 4) + nib(off, 4) + nib(n, 2)


def msg_poke(seg, off, val):
    return [0x47, 6] + nib(seg, 4) + nib(off, 4) + nib(val, 2)


def do_peek(inp, out, seg, off, n):
    send(out, msg_peek(seg, off, n)); r = wait_reply(inp, 0x45)
    if not r:
        print('no reply'); return None
    data = [r[8 + 2 * i] << 4 | r[8 + 2 * i + 1] for i in range(n)]
    print(f'{seg:04x}:{off:04x} ' + ' '.join(f'{b:02x}' for b in data))
    return data


def open_ports(name):
    import mido
    i = next(p for p in mido.get_input_names() if name in p and not p.startswith('CTRL'))
    o = next(p for p in mido.get_output_names() if name in p and not p.startswith('CTRL'))
    return mido.open_input(i), mido.open_output(o)


def send(out, data):
    import mido
    out.send(mido.Message('sysex', data=[0x7D] + data))


def wait_reply(inp, tag, timeout=1.0):
    t = time.time()
    while time.time() - t < timeout:
        for m in inp.iter_pending():
            if m.type == 'sysex' and list(m.data[:3]) == [0x7D, 0x47, tag]:
                return list(m.data[3:])
        time.sleep(0.01)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd'); ap.add_argument('args', nargs='*'); ap.add_argument('--port', default='OCTA-CAPTURE')
    a = ap.parse_args(); h = [int(x, 16) for x in a.args]
    if a.cmd == 'show':
        chip, lo, hi = h
        for s in range(lo, hi + 1):
            print(f'chip{chip} step {s:03x}: {stock_instr(chip, s):06x}')
        return
    inp, out = open_ports(a.port)
    if a.cmd == 'ping':
        send(out, [0x47, 4]); r = wait_reply(inp, 0x44)
        print('backdoor version', r[0] if r else None, '' if r else '(no reply: check cables, MIDI channel 1, ROM v0.2)')
    elif a.cmd == 'write':
        chip, step, instr, coef = h[:4]; commit = h[4] if len(h) > 4 else 8
        send(out, msg_write(chip, step, instr, coef, commit))
        print(f'wrote chip{chip} step {step:03x} instr {instr:06x} coef {coef:04x} commit {commit:02x}')
    elif a.cmd == 'restore':
        chip, step = h
        ins = stock_instr(chip, step)
        send(out, msg_write(chip, step, ins, 0, 0))
        print(f'restored chip{chip} step {step:03x} instr {ins:06x} (coef untouched; change a knob or patch to reload coefs)')
    elif a.cmd == 'raww':
        off, val = h; send(out, [0x47, 2] + nib(off, 4) + nib(val, 2)); print(f'8000:{off:04x} <- {val:02x}')
    elif a.cmd == 'rawr':
        off, = h; send(out, [0x47, 3] + nib(off, 4)); r = wait_reply(inp, 0x43)
        if r:
            v = r[4] << 4 | r[5]; print(f'8000:{off:04x} = {v:02x}')
        else:
            print('no reply')
    elif a.cmd == 'mr':
        seg, off = h[0], h[1]; n = h[2] if len(h) > 2 else 8
        do_peek(inp, out, seg, off, n)
    elif a.cmd == 'mw':
        seg, off, val = h; send(out, msg_poke(seg, off, val)); print(f'{seg:04x}:{off:04x} <- {val:02x}')
    elif a.cmd == 'keys':
        import time as _t
        print('polling FA00:A310..A311 (Ctrl-C to stop) -- hold a button:')
        last = None
        try:
            while True:
                d = do_peek(inp, out, 0xFA00, 0xA310, 2)
                if d and d != last:
                    last = d
                _t.sleep(0.15)
        except KeyboardInterrupt:
            pass
    elif a.cmd == 'jack':
        mode = h[0]
        # 6000:1 channel latch (1=CH1 2=CH2 3=both), 6000:6 relay bits. Known-good combos from E980:3EC6.
        combo = {0: (1, 0x04), 1: (2, 0x08), 2: (3, 0x0C), 3: (3, 0x00)}[mode & 3]
        send(out, msg_poke(0x6000, 1, combo[0])); time.sleep(0.02)
        send(out, msg_poke(0x6000, 6, combo[1]))
        print(f'jack mode {mode}: latch 6000:1={combo[0]:02x} relay 6000:6={combo[1]:02x} (firmware may overwrite on next redraw)')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
