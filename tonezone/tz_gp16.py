"""GP Tone Zone: audition on the unit (MIDI SysEx into the edit buffer, re/pedals.py protocol), save to the library,
add to the OS build (re/tz_sounds/*.json, merged into the pedal/amp lists by re/gen_pedal_data.py)."""
import json, os, re, shutil

from tz_capture import HERE
from tz_fit import P

LIB = os.path.join(HERE, 'library')
OS_DIR = os.path.join(HERE, '..', 're', 'tz_sounds')
NAME_ADDR = 0x64                        # 16-char patch name


def midi_ports():
    import mido
    ins, outs = mido.get_input_names(), mido.get_output_names()
    pick = lambda names: next((n for n in names if 'OCTA-CAPTURE' in n and not n.startswith('CTRL')), names[0] if names else '')
    return ins, outs, pick(ins), pick(outs)


def push(result, in_name, out_name, progress=print):
    """Read the edit buffer, put the fitted sound in (all blocks off first, expression pedal off), write it back.
    The GP-16 must be on its patch screen (ESC twice from the OS) and on MIDI channel 1."""
    import mido
    inp, out = mido.open_input(in_name), mido.open_output(out_name)
    try:
        buf = P.rq1(inp, out)
        if buf is None:
            raise RuntimeError('No reply from the GP-16. Press ESC twice (patch screen), check MIDI ch 1 and both cables.')
        buf[0x0C] = buf[0x0D] = buf[0x0E] = 0
        buf[0x5C] = 127
        P.apply_rec(buf, result['recipe'])
        for i, ch in enumerate(result['name'].ljust(16)[:16]):
            buf[NAME_ADDR + i] = ord(ch)
        P.write_buf(out, buf)
        progress(f'{result["name"]} is in the GP-16 edit buffer. WRITE on the unit stores it to a patch.')
    finally:
        inp.close()
        out.close()


def slug(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') or 'capture'


def to_json(result, cap):
    return {'name': result['name'], 'kind': result['kind'], 'source': cap.file,
            'meta': {k: v for k, v in cap.meta.items() if isinstance(v, (str, int, float))},
            'recipe': {f'0x{a:02x}': int(v) for a, v in sorted(result['recipe'].items())},
            'knobs': [[lab, [list(t) for t in tg]] for lab, tg in result['knobs']],
            'report': result['report'], 'fit': result['fit']}


def save(result, cap):
    os.makedirs(LIB, exist_ok=True)
    path = os.path.join(LIB, slug(result['name']) + '.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(to_json(result, cap), f, indent=1)
    return path


def add_to_os(result, cap):
    """Copy into re/tz_sounds; the next build (re/build_all.py) lists it as a pedal (A2) or a RIG amp."""
    src = save(result, cap)
    os.makedirs(OS_DIR, exist_ok=True)
    dst = os.path.join(OS_DIR, os.path.basename(src))
    shutil.copyfile(src, dst)
    return dst
