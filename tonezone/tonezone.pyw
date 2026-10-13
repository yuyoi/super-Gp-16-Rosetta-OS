"""GP Tone Zone -- turn existing tone captures (NAM .nam, cab IR .wav) into Roland GP-16 sounds for the
JSW ROSETTA OS: analyse, fit the GP-16's own blocks, audition on the unit over MIDI, save, add to the OS build.
Run: py -3.10 tonezone.pyw   (needs numpy, scipy, torch, soundfile, matplotlib, mido + python-rtmidi; NAM is vendored)"""
import os, sys, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import tz_capture as tc
import tz_measure as tm
import tz_fit as tf
import tz_gp16 as tg

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class App(tk.Tk):
    def __init__(self, folder=None):
        super().__init__()
        self.title('GP Tone Zone')
        self.geometry('1060x680')
        self.minsize(900, 560)
        self.caps, self.results = [], {}
        self._busy = False
        # ---- top bar
        top = ttk.Frame(self, padding=6)
        top.pack(fill='x')
        ttk.Button(top, text='Open folder...', command=self.open_folder).pack(side='left')
        self.folder_lbl = ttk.Label(top, text='no folder')
        self.folder_lbl.pack(side='left', padx=8)
        ttk.Label(top, text='MIDI in').pack(side='left', padx=(20, 2))
        self.min = ttk.Combobox(top, width=24, state='readonly')
        self.min.pack(side='left')
        ttk.Label(top, text='out').pack(side='left', padx=(8, 2))
        self.mout = ttk.Combobox(top, width=24, state='readonly')
        self.mout.pack(side='left')
        ttk.Button(top, text='Refresh', command=self.refresh_midi).pack(side='left', padx=4)
        # ---- body
        body = ttk.PanedWindow(self, orient='horizontal')
        body.pack(fill='both', expand=True, padx=6, pady=(0, 6))
        left = ttk.Frame(body)
        body.add(left, weight=1)
        self.lst = tk.Listbox(left, activestyle='dotbox', exportselection=False)
        self.lst.pack(fill='both', expand=True)
        self.lst.bind('<<ListboxSelect>>', lambda e: self.show())
        btns = ttk.Frame(left)
        btns.pack(fill='x', pady=4)
        for txt, cmd in (('Analyse', self.analyse), ('Analyse all', self.analyse_all)):
            ttk.Button(btns, text=txt, command=cmd).pack(side='left', expand=True, fill='x', padx=2)
        right = ttk.Frame(body)
        body.add(right, weight=3)
        self.fig = Figure(figsize=(6.6, 3.0), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.info = tk.Text(right, height=9, wrap='word', font=('Consolas', 9))
        self.info.pack(fill='x')
        act = ttk.Frame(right)
        act.pack(fill='x', pady=4)
        for txt, cmd in (('Push to GP-16', self.push), ('Save to library', self.save), ('Add to OS build', self.add_os)):
            ttk.Button(act, text=txt, command=cmd).pack(side='left', expand=True, fill='x', padx=2)
        self.status = ttk.Label(self, text='Open a folder of .nam captures / .wav IRs.', anchor='w', padding=(8, 2))
        self.status.pack(fill='x')
        self.refresh_midi()
        self.draw(None)
        if folder:
            self.load_folder(folder)

    # ---------------------------------------------------------------- helpers
    def say(self, text):
        self.after(0, lambda: self.status.config(text=text))

    def cur(self):
        sel = self.lst.curselection()
        return self.caps[sel[0]] if sel else None

    def run(self, fn, done=None):
        if self._busy:
            self.say('Busy, wait for the current job.')
            return
        self._busy = True

        def job():
            try:
                r = fn()
                if done:
                    self.after(0, lambda: done(r))
            except Exception as e:
                tb = traceback.format_exc(limit=2)
                self.after(0, lambda: messagebox.showerror('GP Tone Zone', f'{e}\n\n{tb}'))
                self.say(f'Error: {e}')
            finally:
                self._busy = False
        threading.Thread(target=job, daemon=True).start()

    def refresh_midi(self):
        try:
            ins, outs, i0, o0 = tg.midi_ports()
        except Exception as e:
            ins, outs, i0, o0 = [], [], '', ''
            self.say(f'MIDI unavailable: {e}')
        self.min['values'], self.mout['values'] = ins, outs
        self.min.set(i0)
        self.mout.set(o0)

    # ---------------------------------------------------------------- folder / list
    def open_folder(self):
        d = filedialog.askdirectory(title='Folder with .nam captures and .wav IRs')
        if d:
            self.load_folder(d)

    def load_folder(self, d):
        self.caps = tc.find(d)
        self.results = {}
        self.folder_lbl.config(text=d)
        self.lst.delete(0, 'end')
        for c in self.caps:
            self.lst.insert('end', self.row(c))
        self.say(f'{len(self.caps)} captures. Select one and Analyse.')

    def row(self, c):
        r = self.results.get(c.path)
        tag = f'  ->  {r["name"]} ({r["kind"]})' if r else ''
        return f'{c.file}{tag}'

    def show(self):
        c = self.cur()
        if not c:
            return
        r = self.results.get(c.path)
        self.info.delete('1.0', 'end')
        if r:
            self.info.insert('end', '\n'.join(r['report']))
            self.draw(r)
        else:
            meta = ', '.join(f'{k}: {v}' for k, v in c.meta.items() if isinstance(v, (str, int, float)))
            self.info.insert('end', c.describe() + '\n' + meta + '\n\nNot analysed yet.')
            self.draw(None)

    def draw(self, r):
        ax = self.ax
        ax.clear()
        ax.set_xscale('log')
        ax.set_xlim(60, 10000)
        ax.set_ylim(-15, 15)
        ax.grid(True, which='both', alpha=0.3)
        ax.set_xlabel('Hz')
        ax.set_ylabel('dB')
        if r:
            m = r['measure']
            ax.plot(m['freqs'], m['voicing'], 'o', ms=3, label='capture voicing')
            ax.plot(m['freqs'], tf.fitted_curve(m['freqs'], r), '-', lw=2, label='GP-16 EQ fit')
            ax.legend(loc='lower left', fontsize=8)
            ax.set_title(f'{r["name"]}  ({r["kind"]})', fontsize=10)
        else:
            ax.set_title('voicing vs GP-16 EQ fit', fontsize=10)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ---------------------------------------------------------------- actions
    def _analyse(self, c):
        self.say(f'Analysing {c.file} (first run of a model takes a few seconds)...')
        m = tm.measure(c, progress=self.say)
        r = tf.fit(c, m)
        r['measure'] = m
        self.results[c.path] = r
        return c

    def _refresh_row(self, c):
        i = self.caps.index(c)
        sel = self.lst.curselection()
        self.lst.delete(i)
        self.lst.insert(i, self.row(c))
        if sel:
            self.lst.selection_set(sel[0])
        self.show()

    def analyse(self):
        c = self.cur()
        if not c:
            self.say('Select a capture first.')
            return
        self.run(lambda: self._analyse(c), lambda c: (self._refresh_row(c), self.say(f'{c.file}: done.')))

    def analyse_all(self):
        caps = list(self.caps)

        def job():
            for c in caps:
                if c.path not in self.results:
                    try:
                        self._analyse(c)
                        self.after(0, lambda c=c: self._refresh_row(c))
                    except Exception as e:
                        self.say(f'{c.file}: {e}')
            return len(caps)
        self.run(job, lambda n: self.say(f'Analysed {n} captures.'))

    def _need(self):
        c = self.cur()
        r = self.results.get(c.path) if c else None
        if not r:
            self.say('Analyse the selected capture first.')
        return c, r

    def push(self):
        c, r = self._need()
        if not r:
            return
        i, o = self.min.get(), self.mout.get()
        if not i or not o:
            self.say('Pick the MIDI in/out of the interface the GP-16 is on.')
            return
        self.run(lambda: tg.push(r, i, o, progress=self.say))

    def save(self):
        c, r = self._need()
        if r:
            self.say(f'Saved {tg.save(r, c)}')

    def add_os(self):
        c, r = self._need()
        if not r:
            return
        p = tg.add_to_os(r, c)
        messagebox.showinfo('GP Tone Zone', f'{r["name"]} added to the OS build:\n{p}\n\nRebuild (re/build_all.py) and flash; it '
                            f'appears as a {"RIG amp" if r["kind"] == "amp" else "pedal in the A2 DIRT list"}. '
                            f'Adding sounds resets stored knobs and board memories once.')


if __name__ == '__main__':
    App(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
