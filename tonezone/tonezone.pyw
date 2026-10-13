"""GP Tone Zone v0.2 - turn existing tone captures (NAM .nam, cab IR .wav) into Roland GP-16 sounds for the JSW ROSETTA OS:
analyse, fit the GP-16's own blocks, refine them on the real unit through the audio loop, audition over MIDI, save, add to
the OS build. Look and feel follows Rosetta ROM Studio (rosetta_rom/rosetta_studio.pyw).
Run: py -3.10 tonezone.pyw [folder]   |   py -3.10 tonezone.pyw --selftest   (headless chain check, no unit needed)
Needs numpy, scipy, torch, soundfile, matplotlib, mido + python-rtmidi, sounddevice; NAM is vendored in _vendor."""
import json, os, sys, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import tz_capture as tc
import tz_measure as tm
import tz_fit as tf
import tz_gp16 as tg

APP = 'GP Tone Zone'; APP_VERSION = '0.2'; CFG = os.path.join(HERE, 'tonezone_config.json')
try:
    import windnd
except ImportError:
    windnd = None

# ---- Rosetta ROM Studio theme in the GP-16's own colours (sampled from the unit): warm black panel, white legends,
# Roland orange for the logo and labels, the saturated green LCD and green 7-segment patch display
PANEL, PANEL_HI, RECESS, EDGE = '#1c1a17', '#2b2824', '#110f0d', '#070605'
TEXT, DIM, SILK = '#ebe7dd', '#958e80', '#f07a2c'
RED, ORANGE = '#d8342a', '#f07a2c'
LCD_A, LCD_B, LCD_CELL, LCD_INK = '#3cf038', '#12c816', '#22dc22', '#062c06'
SEG_ON, SEG_OFF = '#4cff4a', '#132412'
WAVE_BG, WAVE_FG, GRID = '#0d0c0b', '#3cf038', '#24211c'


def apply_theme(root):
    st = ttk.Style(root); st.theme_use('clam'); root.configure(bg=PANEL)
    st.configure('.', background=PANEL, foreground=TEXT, fieldbackground=RECESS, bordercolor=EDGE, lightcolor=PANEL_HI,
                 darkcolor=EDGE, troughcolor=RECESS, focuscolor=ORANGE, selectbackground=ORANGE, selectforeground='#111',
                 insertcolor=TEXT, arrowcolor=TEXT, font=('Segoe UI', 9))
    st.configure('TLabelframe', background=PANEL, bordercolor='#46494e')
    st.configure('TLabelframe.Label', background=PANEL, foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('TButton', background='#33302b', foreground=TEXT, bordercolor=EDGE, lightcolor='#4a463f', darkcolor='#151310',
                 padding=(9, 3), font=('Arial', 9, 'bold'))
    st.map('TButton', background=[('pressed', '#1f1d1a'), ('active', '#423e37')])
    st.configure('Build.TButton', background='#36322c', foreground=ORANGE, font=('Bahnschrift', 13, 'bold'), padding=(20, 10),
                 lightcolor='#4d4840', darkcolor='#14120f', bordercolor=ORANGE)
    st.map('Build.TButton', background=[('pressed', '#1f1d1a'), ('active', '#45403a')])
    st.configure('Treeview', background=RECESS, fieldbackground=RECESS, foreground=TEXT, rowheight=21, bordercolor=EDGE)
    st.map('Treeview', background=[('selected', '#8a3f14')], foreground=[('selected', '#ffffff')])
    st.configure('Treeview.Heading', background=PANEL_HI, foreground=SILK, font=('Segoe UI', 8, 'bold'), relief='flat')
    st.map('Treeview.Heading', background=[('active', '#44474c')])
    for w in ('TEntry', 'TCombobox'):
        st.configure(w, fieldbackground=RECESS, foreground=TEXT, background='#46423b', arrowcolor=TEXT)
    st.map('TCombobox', fieldbackground=[('readonly', RECESS)], foreground=[('readonly', TEXT)],
           selectbackground=[('readonly', RECESS)], selectforeground=[('readonly', TEXT)])
    st.configure('TScrollbar', background='#46423b', troughcolor=RECESS, arrowcolor=TEXT)
    st.configure('Dim.TLabel', foreground=DIM); st.configure('Silk.TLabel', foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('Title.TLabel', foreground=ORANGE, font=('Bahnschrift SemiLight SemiConde', 30))
    st.configure('Sub.TLabel', foreground=ORANGE, font=('Bahnschrift', 10))
    st.configure('Roland.TLabel', foreground=TEXT, font=('Arial Black', 11))
    st.configure('Status.TFrame', background=RECESS); st.configure('Status.TLabel', background=RECESS, foreground=DIM)


def dark_titlebar(win):
    try:
        import ctypes
        win.update_idletasks(); hwnd = ctypes.windll.user32.GetParent(win.winfo_id()); v = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0:
                break
    except Exception:
        pass


class LCD(tk.Canvas):
    """the GP-16's own display: 16 x 2"""
    CW, CH = 13, 22

    def __init__(self, master, cols=16):
        self.cols = cols
        super().__init__(master, width=cols * self.CW + 26, height=2 * self.CH + 22, bg=PANEL, highlightthickness=0)
        self.lines = ['', '']; self.text_ids = []; W, H = int(self['width']), int(self['height'])
        self.create_rectangle(0, 0, W, H, fill=EDGE, outline='#0b0b0c'); x0, y0, x1, y1 = 6, 6, W - 6, H - 6; n = y1 - y0
        a = [int(LCD_A[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(LCD_B[i:i + 2], 16) for i in (1, 3, 5)]
        for i in range(n):
            t = abs(i / n - 0.35) * 1.3
            self.create_line(x0, y0 + i, x1, y0 + i, fill='#%02x%02x%02x' % tuple(int(a[k] * (1 - t) + b[k] * t) for k in range(3)))
        for r in range(2):
            for c in range(cols):
                cx, cy = 13 + c * self.CW, 11 + r * self.CH
                self.create_rectangle(cx, cy, cx + self.CW - 2, cy + self.CH - 3, fill=LCD_CELL, outline='')

    def set(self, l1, l2):
        lines = [l1[:self.cols].ljust(self.cols), l2[:self.cols].ljust(self.cols)]
        if lines == self.lines:
            return
        self.lines = lines
        for i in self.text_ids:
            self.delete(i)
        self.text_ids = []
        for r, s in enumerate(lines):
            for c, ch in enumerate(s):
                if ch != ' ':
                    self.text_ids.append(self.create_text(13 + c * self.CW + (self.CW - 2) / 2, 11 + r * self.CH + (self.CH - 3) / 2,
                                                          text=ch, fill=LCD_INK, font=('Consolas', 13, 'bold')))


class SevenSeg(tk.Canvas):
    """the GP-16's 2-digit green patch display"""
    SEGS = {'0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg', '4': 'bcfg', '5': 'acdfg', '6': 'acdefg', '7': 'abc',
            '8': 'abcdefg', '9': 'abcdfg', '-': 'g', ' ': ''}

    def __init__(self, master, digits=2):
        self.digits = digits; self.text = None
        super().__init__(master, width=digits * 30 + 14, height=2 * 22 + 22, bg=PANEL, highlightthickness=0); self.set('--')

    def set(self, text):
        text = str(text)[-self.digits:].rjust(self.digits)
        if text == self.text:
            return
        self.text = text; self.delete('all')
        W, H = int(self['width']), int(self['height'])
        self.create_rectangle(0, 0, W, H, fill=EDGE, outline='#0b0b0c'); self.create_rectangle(5, 5, W - 5, H - 5, fill='#050805', outline='')
        for k, ch in enumerate(text):
            x, y, w, h, t = 12 + k * 30, 11, 18, 21, 4                           # digit box, segment thickness
            seg = {'a': (x + t, y, x + w - t, y + t), 'g': (x + t, y + h - t / 2, x + w - t, y + h + t / 2),
                   'd': (x + t, y + 2 * h - t, x + w - t, y + 2 * h), 'f': (x, y + t, x + t, y + h - 1),
                   'b': (x + w - t, y + t, x + w, y + h - 1), 'e': (x, y + h + 1, x + t, y + 2 * h - t),
                   'c': (x + w - t, y + h + 1, x + w, y + 2 * h - t)}
            on = self.SEGS.get(ch, '')
            for n, (x0, y0, x1, y1) in seg.items():
                self.create_rectangle(x0, y0, x1, y1, fill=SEG_ON if n in on else SEG_OFF, outline='')


class LEDMeter(tk.Canvas):
    def __init__(self, master, segs=26):
        self.segs = segs
        super().__init__(master, width=segs * 8 + 4, height=18, bg=PANEL, highlightthickness=0); self.set(0)

    def set(self, frac, dim=False):
        """frac 0-1 = how good the match is (green end = close)"""
        self.delete('all'); lit = int(round(frac * self.segs))
        for i in range(self.segs):
            p = i / self.segs; on = i < lit and not dim
            col = ('#c8322a' if p < 0.3 else '#f0b12a' if p < 0.6 else '#6fd13a') if on else \
                  ('#3a1e1c' if p < 0.3 else '#3a3218' if p < 0.6 else '#1f3319')
            self.create_rectangle(2 + i * 8, 2, 2 + i * 8 + 6, 16, fill=col, outline='')


def load_cfg():
    try:
        with open(CFG) as f:
            return json.load(f)
    except Exception:
        return {}


def lcd_name(s):
    return ''.join(ch for ch in s.upper() if 32 <= ord(ch) < 127)


class App(tk.Tk):
    def __init__(s, folder=None):
        super().__init__(); s.geometry('1180x%d' % min(740, s.winfo_screenheight() - 140)); s.minsize(980, 580); s.title(APP)
        apply_theme(s); dark_titlebar(s)
        s.cfg = load_cfg(); s.caps, s.results = [], {}; s.unit = None; s._busy = False; s.folder = None
        s.filt = tk.StringVar(value='All')
        s.menu(); s.ui(); s.refresh_midi(); s.draw(None); s.update_head()
        s.protocol('WM_DELETE_WINDOW', s.quit_app)
        if windnd:
            windnd.hook_dropfiles(s, func=lambda files: s.after(30, lambda: s.on_drop(files)))
        folder = folder or s.cfg.get('folder')
        if folder and os.path.isdir(folder):
            s.load_folder(folder)

    # ---------------------------------------------------------------- layout
    def menu(s):
        mb = tk.Menu(s); f = tk.Menu(mb, tearoff=0)
        for l, c, a in (('Open capture folder...', s.open_folder, 'Ctrl+O'), (None,) * 3,
                        ('Analyse selected', s.analyse, 'F5'), ('Analyse all', s.analyse_all, 'Shift+F5'), (None,) * 3,
                        ('Save to library', s.save, 'Ctrl+S'), ('Add to OS build', s.add_os, 'Ctrl+B'), (None,) * 3,
                        ('Exit', s.quit_app, '')):
            f.add_separator() if l is None else f.add_command(label=l, command=c, accelerator=a)
        mb.add_cascade(label='File', menu=f)
        u = tk.Menu(mb, tearoff=0)
        for l, c, a in (('Calibrate loop...', s.calibrate, ''), ('Push to GP-16', s.push, 'Ctrl+P'),
                        ('Refine on unit', s.refine, 'Ctrl+R'), (None,) * 3, ('Refresh MIDI ports', s.refresh_midi, '')):
            u.add_separator() if l is None else u.add_command(label=l, command=c, accelerator=a)
        mb.add_cascade(label='Unit', menu=u)
        h = tk.Menu(mb, tearoff=0); h.add_command(label='How it works', command=s.help); mb.add_cascade(label='Help', menu=h)
        s.config(menu=mb)
        for k, fn in (('<Control-o>', s.open_folder), ('<F5>', s.analyse), ('<Shift-F5>', s.analyse_all), ('<Control-s>', s.save),
                      ('<Control-b>', s.add_os), ('<Control-p>', s.push), ('<Control-r>', s.refine)):
            s.bind(k, lambda e, fn=fn: fn())

    def ui(s):
        head = ttk.Frame(s, padding=(12, 10, 12, 4)); head.pack(fill='x'); plate = ttk.Frame(head); plate.pack(side='left', padx=(0, 16))
        ttk.Label(plate, text='Roland', style='Roland.TLabel').pack(anchor='w')
        ttk.Label(plate, text='GP-16', style='Title.TLabel').pack(anchor='w'); ttk.Label(plate, text='GP TONE ZONE', style='Sub.TLabel').pack(anchor='w')
        s.seg = SevenSeg(head); s.seg.pack(side='left', padx=(0, 10))
        s.lcd = LCD(head); s.lcd.pack(side='left'); mf = ttk.Frame(head); mf.pack(side='left', padx=16)
        ttk.Label(mf, text='MATCH', style='Silk.TLabel').pack(anchor='w'); s.meter = LEDMeter(mf); s.meter.pack(anchor='w', pady=(2, 2))
        s.v_match = tk.StringVar(); ttk.Label(mf, textvariable=s.v_match, style='Dim.TLabel').pack(anchor='w')
        bf = ttk.Frame(head); bf.pack(side='right'); ttk.Label(bf, text='ON THE UNIT', style='Silk.TLabel').pack()
        ttk.Button(bf, text='REFINE', style='Build.TButton', command=s.refine).pack(pady=(2, 0))
        stf = ttk.Frame(s, style='Status.TFrame'); stf.pack(fill='x', side='bottom')
        s.v_st = tk.StringVar(value='Open a folder of .nam captures / .wav IRs (File > Open, or drop it on the window).')
        ttk.Label(stf, textvariable=s.v_st, style='Status.TLabel', padding=(8, 3)).pack(side='left')
        main = ttk.PanedWindow(s, orient='horizontal'); main.pack(fill='both', expand=True, padx=8, pady=(4, 4))
        # left: captures + unit
        left = ttk.Frame(main); main.add(left, weight=1)
        lf = ttk.Labelframe(left, text=' CAPTURES ', padding=6); lf.pack(fill='both', expand=True)
        fb = ttk.Frame(lf); fb.pack(fill='x', pady=(0, 4)); ttk.Label(fb, text='SHOW', style='Silk.TLabel').pack(side='left')
        cb = ttk.Combobox(fb, textvariable=s.filt, values=['All', 'Analysed', 'Refined', 'Pedals', 'Amps + IRs'], width=12, state='readonly')
        cb.pack(side='left', padx=6); cb.bind('<<ComboboxSelected>>', lambda e: s.fill())
        cols = (('file', 'Capture', 150), ('type', 'Type', 54), ('gp', 'GP-16', 70), ('match', 'Match', 58))
        s.tv = ttk.Treeview(lf, columns=[c[0] for c in cols], show='headings', selectmode='browse')
        for c, t, w in cols:
            s.tv.heading(c, text=t); s.tv.column(c, width=w, anchor='w' if c == 'file' else 'center')
        sb = ttk.Scrollbar(lf, command=s.tv.yview); s.tv.configure(yscrollcommand=sb.set); sb.pack(side='right', fill='y')
        s.tv.pack(fill='both', expand=True)
        s.tv.bind('<<TreeviewSelect>>', lambda e: s.show()); s.tv.bind('<Double-1>', lambda e: s.analyse())
        uf = ttk.Labelframe(left, text=' UNIT ', padding=6); uf.pack(fill='x', pady=(6, 0))
        for r, (lab, attr) in enumerate((('MIDI IN', 'min'), ('MIDI OUT', 'mout'))):
            ttk.Label(uf, text=lab, style='Silk.TLabel').grid(row=r, column=0, sticky='w', pady=1)
            w = ttk.Combobox(uf, width=26, state='readonly'); w.grid(row=r, column=1, columnspan=2, sticky='we', padx=6, pady=1)
            setattr(s, attr, w)
        ttk.Label(uf, text='AUDIO', style='Silk.TLabel').grid(row=2, column=0, sticky='w', pady=1)
        s.audio = ttk.Entry(uf, width=14); s.audio.insert(0, s.cfg.get('audio', 'Focusrite')); s.audio.grid(row=2, column=1, sticky='w', padx=6)
        ttk.Button(uf, text='Refresh', command=s.refresh_midi).grid(row=2, column=2, sticky='e')
        s.v_cal = tk.StringVar(); ttk.Label(uf, textvariable=s.v_cal, style='Dim.TLabel', wraplength=300).grid(row=3, column=0, columnspan=3, sticky='w', pady=(4, 0))
        ttk.Button(uf, text='Calibrate loop...', command=s.calibrate).grid(row=4, column=0, columnspan=3, sticky='we', pady=(4, 0))
        uf.columnconfigure(1, weight=1)
        # right: voicing plot + report + actions
        rf = ttk.Labelframe(main, text=' VOICING ', padding=6); main.add(rf, weight=3)
        import matplotlib
        matplotlib.use('TkAgg')
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        s.fig = Figure(figsize=(6.6, 3.0), dpi=100, facecolor=PANEL)
        s.ax = s.fig.add_subplot(111)
        s.canvas = FigureCanvasTkAgg(s.fig, master=rf); s.canvas.get_tk_widget().configure(bg=PANEL, highlightthickness=0)
        s.canvas.get_tk_widget().pack(fill='both', expand=True)
        s.info = tk.Text(rf, height=8, wrap='word', font=('Consolas', 9), bg=RECESS, fg=TEXT, insertbackground=TEXT,
                         relief='flat', highlightthickness=1, highlightbackground=EDGE)
        s.info.pack(fill='x', pady=(6, 0))
        row = ttk.Frame(rf); row.pack(fill='x', pady=(8, 0))
        for t, c in (('Analyse', s.analyse), ('Push to GP-16', s.push), ('Refine on unit', s.refine),
                     ('Save to library', s.save), ('Add to OS build', s.add_os)):
            ttk.Button(row, text=t, command=c).pack(side='left', padx=(0, 6))

    # ---------------------------------------------------------------- helpers
    def say(s, text):
        s.after(0, lambda: s.v_st.set(text))

    def run(s, fn, done=None):
        if s._busy:
            s.say('Busy, wait for the current job.')
            return
        s._busy = True

        def job():
            try:
                r = fn()
                if done:
                    s.after(0, lambda: done(r))
            except Exception as e:
                tb = traceback.format_exc(limit=2)
                s.after(0, lambda: messagebox.showerror(APP, f'{e}\n\n{tb}'))
                s.say(f'Error: {e}')
            finally:
                s._busy = False
        threading.Thread(target=job, daemon=True).start()

    def save_cfg(s):
        s.cfg.update(folder=s.folder, midi_in=s.min.get(), midi_out=s.mout.get(), audio=s.audio.get())
        try:
            with open(CFG, 'w') as f:
                json.dump(s.cfg, f, indent=1)
        except OSError:
            pass

    def refresh_midi(s):
        try:
            ins, outs, i0, o0 = tg.midi_ports()
        except Exception as e:
            ins, outs, i0, o0 = [], [], '', ''
            s.say(f'MIDI unavailable: {e}')
        s.min['values'], s.mout['values'] = ins, outs
        s.min.set(s.cfg.get('midi_in') if s.cfg.get('midi_in') in ins else i0)
        s.mout.set(s.cfg.get('midi_out') if s.cfg.get('midi_out') in outs else o0)
        s.unit = None
        s.update_cal()

    def update_cal(s):
        import tz_loop as tl
        c = tl.load_cal()
        if c and 'ref_db' in c:
            s.v_cal.set(f'Loop calibrated {c.get("when", "")}: guitar +{tm.GUITAR_PEAK_DBU:.0f} dBu = {c["peak_dbfs"]:+.0f} dBFS, '
                        f'loop gain {c["gain_db"]:+.1f} dB. Keep the GP-16 volume + interface gains as they were.')
        else:
            s.v_cal.set('Loop not calibrated: wire it (Help), GP-16 on its patch screen, then Calibrate loop.')

    def cur(s):
        sel = s.tv.selection()
        return s.caps[int(sel[0])] if sel else None

    def ctype(s, c):
        return 'IR' if c.kind == 'ir' else (c.meta.get('gear_type') or 'nam')

    def gp(s, r):
        if not r:
            return ''
        if r['kind'] == 'amp':
            return 'RIG AMP'
        return f'{(r["fit"].get("dirt") or "dist").upper()} {r["fit"].get("drive", "")}'

    def match(s, r):
        if not r:
            return None, ''
        if r.get('refine'):
            e = r['refine']['passes'][r['refine']['best']]['err']
            return e, f'{e:.1f} dB'
        return r['fit'].get('rms_err_db'), f'~{r["fit"].get("rms_err_db", 0):.1f}'

    def row_vals(s, c):
        r = s.results.get(c.path)
        return (c.file, s.ctype(c), s.gp(r), s.match(r)[1])

    def fill(s):
        sel = s.cur()
        s.tv.delete(*s.tv.get_children())
        f = s.filt.get()
        for i, c in enumerate(s.caps):
            r = s.results.get(c.path)
            if (f == 'Analysed' and not r) or (f == 'Refined' and not (r and r.get('refine'))) or \
               (f == 'Pedals' and s.ctype(c) not in ('pedal', 'nam')) or (f == 'Amps + IRs' and s.ctype(c) not in ('amp', 'IR')):
                continue
            s.tv.insert('', 'end', iid=str(i), values=s.row_vals(c))
        if sel and str(s.caps.index(sel)) in s.tv.get_children():
            s.tv.selection_set(str(s.caps.index(sel)))

    def refresh_row(s, c):
        i = str(s.caps.index(c))
        if i in s.tv.get_children():
            s.tv.item(i, values=s.row_vals(c))
        s.show()

    def update_head(s):
        c = s.cur(); r = s.results.get(c.path) if c else None
        s.seg.set('%02d' % (s.caps.index(c) + 1) if c else '--')
        if not c:
            s.lcd.set(' GP TONE ZONE', 'OPEN A FOLDER' if not s.caps else 'PICK A CAPTURE'); s.meter.set(0, dim=True)
            s.v_match.set('no capture selected'); return
        l1 = lcd_name(r['name'] if r else c.name)
        if not r:
            s.lcd.set(l1, 'NOT ANALYSED'); s.meter.set(0, dim=True); s.v_match.set('F5 = analyse'); return
        e, _ = s.match(r)
        l2 = 'RIG AMP' if r['kind'] == 'amp' else f'A2 {s.gp(r)}'
        if r.get('refine'):
            l2 = (l2 + f' {e:.1f}dB')[:16]
            s.v_match.set(f'{e:.1f} dB rms off the capture, measured on the unit')
            s.meter.set(float(np.clip(1 - e / 10, 0, 1)))
        else:
            s.v_match.set(f'EQ model fit {e:.1f} dB (not measured yet: REFINE)')
            s.meter.set(float(np.clip(1 - e / 10, 0, 1)), dim=False)
        s.lcd.set(l1, l2)

    def draw(s, r):
        ax = s.ax; ax.clear(); ax.set_facecolor(WAVE_BG)
        for sp in ax.spines.values():
            sp.set_color(EDGE)
        ax.tick_params(colors=DIM, labelsize=8)
        ax.set_xscale('log'); ax.set_xlim(60, 10000); ax.set_ylim(-15, 15)
        ax.grid(True, which='both', color=GRID, lw=0.8)
        ax.set_xlabel('Hz', color=DIM, fontsize=8); ax.set_ylabel('dB', color=DIM, fontsize=8)
        if r and r.get('refine'):
            m, rf = r['measure'], r['refine']; best = rf['passes'][rf['best']]
            ax.plot(m['freqs'], rf['target'], 'o', ms=3, color=ORANGE, label='capture (tone curve)')
            ax.plot(m['freqs'], rf['passes'][0]['curve'], ':', lw=1, color=DIM, label='GP-16 before refine (measured)')
            ax.plot(m['freqs'], best['curve'], '-', lw=2, color=WAVE_FG, label=f'GP-16 refined (measured, {best["err"]:.1f} dB rms)')
        elif r:
            m = r['measure']
            ax.plot(m['freqs'], m['voicing'], 'o', ms=3, color=ORANGE, label='capture voicing')
            ax.plot(m['freqs'], tf.fitted_curve(m['freqs'], r), '-', lw=2, color=WAVE_FG, label='GP-16 EQ fit (model)')
        if r:
            leg = ax.legend(loc='lower left', fontsize=8, facecolor=RECESS, edgecolor=EDGE)
            for t in leg.get_texts():
                t.set_color(TEXT)
        s.fig.tight_layout(); s.canvas.draw_idle()

    def show(s):
        c = s.cur(); s.update_head()
        if not c:
            return
        r = s.results.get(c.path)
        s.info.delete('1.0', 'end')
        if r:
            s.info.insert('end', '\n'.join(r['report']))
        else:
            meta = ', '.join(f'{k}: {v}' for k, v in c.meta.items() if isinstance(v, (str, int, float)))
            s.info.insert('end', c.describe() + '\n' + meta + '\n\nNot analysed yet (F5).')
        s.draw(r)

    # ---------------------------------------------------------------- folder / list
    def open_folder(s):
        d = filedialog.askdirectory(title='Folder with .nam captures and .wav IRs', initialdir=s.folder or HERE)
        if d:
            s.load_folder(d)

    def on_drop(s, files):
        f = files[0].decode('mbcs') if isinstance(files[0], bytes) else files[0]
        s.load_folder(f if os.path.isdir(f) else os.path.dirname(f))

    def load_folder(s, d):
        s.caps = tc.find(d); s.results = {}; s.folder = d; s.save_cfg()
        s.title(f'{APP} - {os.path.basename(d)}')
        s.fill()
        if s.caps:
            s.tv.selection_set('0')
        s.say(f'{len(s.caps)} captures in {d}. Select one and Analyse (F5).')

    # ---------------------------------------------------------------- actions
    def _analyse(s, c):
        s.say(f'Analysing {c.file} (first run of a model takes a few seconds)...')
        m = tm.measure(c, progress=s.say)
        r = tf.fit(c, m); r['measure'] = m
        s.results[c.path] = r
        return c

    def analyse(s):
        c = s.cur()
        if not c:
            s.say('Select a capture first.'); return
        s.run(lambda: s._analyse(c), lambda c: (s.refresh_row(c), s.say(f'{c.file}: analysed. REFINE measures it on the unit.')))

    def analyse_all(s):
        caps = list(s.caps)

        def job():
            for c in caps:
                if c.path not in s.results:
                    try:
                        s._analyse(c)
                        s.after(0, lambda c=c: s.refresh_row(c))
                    except Exception as e:
                        s.say(f'{c.file}: {e}')
            return len(caps)
        s.run(job, lambda n: s.say(f'Analysed {n} captures.'))

    def _need(s):
        c = s.cur(); r = s.results.get(c.path) if c else None
        if not r:
            s.say('Analyse the selected capture first (F5).')
        return c, r

    def _unit(s):
        import tz_loop as tl
        if s.unit is None:
            s.save_cfg()
            s.unit = tl.Unit(s.audio.get() or 'Focusrite', s.min.get(), s.mout.get())
        return s.unit

    def push(s):
        c, r = s._need()
        if not r:
            return
        i, o = s.min.get(), s.mout.get()
        if not i or not o:
            s.say('Pick the MIDI in/out of the interface the GP-16 is on (UNIT box).'); return
        s.save_cfg(); s.run(lambda: tg.push(r, i, o, progress=s.say))

    def calibrate(s):
        import tz_loop as tl
        if not messagebox.askokcancel(APP, 'Calibrate the audio loop:\n- interface OUT 1 -> GP-16 INPUT, GP-16 OUT A '
                                      '-> interface IN 1/2, MIDI both ways\n- GP-16 on its patch screen (ESC twice from the OS)'
                                      '\n\nPlays tones for about 30 s. Keep the GP-16 output volume and the interface gains '
                                      'where they are afterwards.'):
            return
        s.unit = None
        s.run(lambda: tl.calibrate(s._unit(), progress=s.say), lambda c: s.update_cal())

    def refine(s):
        import tz_loop as tl
        c, r = s._need()
        if not r:
            return

        def job():
            u = s._unit()
            if not u.cal or 'ref_db' not in u.cal:
                raise RuntimeError('Calibrate the loop first (UNIT box).')
            rr = tl.refine(c, r['measure'], r, u, iters=3, progress=s.say)
            rr['measure'] = r['measure']
            s.results[c.path] = rr
            tg.push(rr, u.min, u.mout, progress=lambda t: None)       # leave the kept pass on the unit
            return c
        s.run(job, lambda c: (s.refresh_row(c), s.say(f'{c.file}: refined on the unit; the result is in the GP-16 edit '
                                                      f'buffer (WRITE stores it).')))

    def save(s):
        c, r = s._need()
        if r:
            s.say(f'Saved {tg.save(r, c)}')

    def add_os(s):
        c, r = s._need()
        if not r:
            return
        p = tg.add_to_os(r, c)
        messagebox.showinfo(APP, f'{r["name"]} added to the OS build:\n{p}\n\nRebuild (re/build_all.py) and flash; it '
                                 f'appears as a {"RIG amp" if r["kind"] == "amp" else "pedal in the A2 DIRT list"}. '
                                 f'Adding sounds resets stored knobs and board memories once.')

    def quit_app(s):
        s.save_cfg(); s.destroy()

    def help(s):
        messagebox.showinfo('How it works',
            'CAPTURES: NAM files (.nam, e.g. from TONE3000) and cab IRs (.wav). Open a folder or drop it on the window.\n\n'
            'ANALYSE (F5) plays a calibrated guitar through the capture (+2 dBu peaks, the capture\'s own dBu scale) and a '
            '220 Hz sine from 60 dB under to 6 dB over that, then fits the GP-16: dirt type + drive, the 4-band EQ (its real '
            'DSP response), level. MATCH shows the model error until the sound is measured on the unit.\n\n'
            'REFINE (Ctrl+R) needs the audio loop: interface OUT 1 -> GP-16 INPUT (guitar cable), GP-16 CH1 OUT A/B -> '
            'interface IN 1/2, MIDI both ways, GP-16 on its patch screen (ESC twice from the OS), MIDI channel 1. '
            'Calibrate loop once per setup. Refine locks the drive first (the clipping curve vs the capture\'s, level held '
            'at the Big Muff reference), then corrects the EQ and level in passes and keeps the best one, measured.\n\n'
            'PUSH (Ctrl+P) puts the sound in the GP-16 edit buffer; WRITE on the unit stores it. ADD TO OS BUILD (Ctrl+B) '
            'lists it in the OS after the next build + flash.\n\n'
            'Captures keep their own licenses: don\'t share sounds derived from them against those terms.')


def selftest():
    """headless: synthetic capture -> measure -> fit, no unit"""
    import tz_synth
    cap = tz_synth.SynthCapture()
    m = tm.measure(cap, progress=lambda t: None)
    r = tf.fit(cap, m)
    ok = r['kind'] == 'pedal' and 0x0E in r['recipe'] and len(r['fit']['eq']) == 10 and r['fit']['rms_err_db'] < 6
    print('\n'.join(r['report']))
    print('SELFTEST', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    try:                                                      # own taskbar identity
        import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JSW.GPToneZone')
    except Exception:
        pass
    App(next((a for a in sys.argv[1:] if not a.startswith('--')), None)).mainloop()
