import sys, pitchmap as M, dsplive as D, revload as RL
STEPS = [(1, s) for s in (0x14e, 0x14f, 0x151, 0x152, 0x153, 0x154, 0x155, 0x156, 0x157)] + \
        [(2, s) for s in (0x000, 0x001, 0x002, 0x003, 0x004, 0x018, 0x019, 0x01a, 0x01b, 0x01c)]
io = RL.ports(); RL.stop(io); io[0].close(); io[1].close(); D.forget()
M.test('baseline', [])
for c, s in STEPS:
    i = M.instr(c, s)
    for b in range(24):
        M.test(f'{c}:{s:03x} {i:06x} ^bit{b:2d}', [(c, s, {'instr': i ^ (1 << b)})])
    M.test(f'-- check after {c}:{s:03x}', [])
