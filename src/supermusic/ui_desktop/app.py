# app.py
import glob
import os
import shlex
import subprocess
import sys
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk

# ---------- Appearance ----------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_TITLE = "SuperMusic Tools"

# Resolve project root = parent of this file's directory
PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SRC_DIR = os.path.join(PROJ_ROOT, "src")  # where your scripts live (metadata.py, etc.)


# ---------- Utilities ----------
def which_python() -> str:
    # Use current interpreter to run your scripts (works inside venv)
    return sys.executable


def discover_scripts(src_dir=SRC_DIR):
    # All top-level *.py in src (skip __init__.py)
    scripts = []
    for p in sorted(glob.glob(os.path.join(src_dir, "*.py"))):
        name = os.path.basename(p)
        if name == "__init__.py":
            continue
        scripts.append(name)
    return scripts


class Runner:
    def __init__(self, log_widget, run_button):
        self.log_widget = log_widget
        self.run_button = run_button
        self.proc = None

    def _append(self, text):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def run_async(self, cmd, env=None, cwd=None):
        self.run_button.configure(state="disabled")
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

        def _target():
            try:
                self._append(f"$ {cmd}\n\n")
                self.proc = subprocess.Popen(
                    shlex.split(cmd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                    cwd=cwd,
                )
                for line in self.proc.stdout:
                    self._append(line)
                rc = self.proc.wait()
                self._append(f"\n---\nExit code: {rc}\n")
                if rc != 0:
                    messagebox.showerror("Run failed", f"Command exited with {rc}")
            except FileNotFoundError as e:
                messagebox.showerror("Not found", str(e))
            except Exception as e:
                messagebox.showerror("Error", str(e))
            finally:
                self.run_button.configure(state="normal")
                self.proc = None

        t = threading.Thread(target=_target, daemon=True)
        t.start()


# ---------- App ----------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x680")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=16)

        # Dedicated tabs for known scripts (nice forms)
        self.meta_tab = self.tabs.add("YouTube Metadata")
        self.segm_tab = self.tabs.add("Mixtape Segmenter")

        # Generic tab for any script under src/
        self.scripts_tab = self.tabs.add("Scripts")

        self._build_metadata_tab()
        self._build_segmenter_tab()
        self._build_scripts_tab()

    # ---------- Metadata GUI ----------
    def _build_metadata_tab(self):
        frm = ctk.CTkFrame(self.meta_tab)
        frm.pack(fill="both", expand=False, padx=12, pady=12)

        # Input CSV
        ctk.CTkLabel(frm, text="Input CSV").grid(
            row=0, column=0, sticky="w", padx=6, pady=6
        )
        self.in_csv = ctk.CTkEntry(frm, width=620)
        self.in_csv.grid(row=0, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm,
            text="Browse",
            command=lambda: self._pick_file(
                self.in_csv, [("CSV files", "*.csv"), ("All files", "*.*")]
            ),
        ).grid(row=0, column=2, padx=6, pady=6)

        # Output path (file or directory)
        ctk.CTkLabel(frm, text="Output (file or directory)").grid(
            row=1, column=0, sticky="w", padx=6, pady=6
        )
        self.out_path = ctk.CTkEntry(frm, width=620)
        self.out_path.grid(row=1, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm, text="Browse", command=lambda: self._pick_save_or_dir(self.out_path)
        ).grid(row=1, column=2, padx=6, pady=6)

        # Region
        ctk.CTkLabel(frm, text="Region").grid(
            row=2, column=0, sticky="w", padx=6, pady=6
        )
        self.region = ctk.CTkOptionMenu(
            frm, values=["US", "GB", "CA", "AU", "DE", "FR", "ES", "BR", "JP", "IN"]
        )
        self.region.set("US")
        self.region.grid(row=2, column=1, sticky="w", padx=6, pady=6)

        # yt-dlp checkbox
        self.use_ytdlp = ctk.CTkCheckBox(frm, text="Use yt-dlp to enrich music fields")
        self.use_ytdlp.grid(row=3, column=1, sticky="w", padx=6, pady=6)

        frm.grid_columnconfigure(1, weight=1)

        # Run + Log
        self.meta_run_btn = ctk.CTkButton(
            self.meta_tab, text="Run Metadata Enrichment", command=self._run_metadata
        )
        self.meta_run_btn.pack(padx=12, pady=(0, 8))

        self.meta_log = ctk.CTkTextbox(self.meta_tab, height=360)
        self.meta_log.pack(fill="both", expand=True, padx=12, pady=8)
        self.meta_runner = Runner(self.meta_log, self.meta_run_btn)

    def _run_metadata(self):
        csv_in = self.in_csv.get().strip()
        out = self.out_path.get().strip()
        region = self.region.get().strip() or "US"
        use_ytdlp = self.use_ytdlp.get() == 1

        if not os.path.isfile(csv_in):
            messagebox.showerror(
                "Missing input", "Please choose a valid input CSV file."
            )
            return
        if not out:
            messagebox.showerror(
                "Missing output", "Please choose an output file or directory."
            )
            return

        meta_py = os.path.join(SRC_DIR, "metadata.py")
        if not os.path.isfile(meta_py):
            messagebox.showerror("Not found", f"Could not find {meta_py}")
            return

        cmd = f"{shlex.quote(which_python())} {shlex.quote(meta_py)} --input {shlex.quote(csv_in)} --output {shlex.quote(out)} --region {shlex.quote(region)}"
        if use_ytdlp:
            cmd += " --use-yt-dlp"

        env = os.environ.copy()  # inherit YOUTUBE_API_KEY, etc.
        self.meta_runner.run_async(cmd, env=env, cwd=SRC_DIR)

    # ---------- Segmenter GUI ----------
    def _build_segmenter_tab(self):
        frm = ctk.CTkFrame(self.segm_tab)
        frm.pack(fill="both", expand=False, padx=12, pady=12)

        # Audio file
        ctk.CTkLabel(frm, text="Audio file").grid(
            row=0, column=0, sticky="w", padx=6, pady=6
        )
        self.audio_path = ctk.CTkEntry(frm, width=620)
        self.audio_path.grid(row=0, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm,
            text="Browse",
            command=lambda: self._pick_file(
                self.audio_path,
                [("Audio", "*.mp3 *.wav *.flac *.m4a"), ("All files", "*.*")],
            ),
        ).grid(row=0, column=2, padx=6, pady=6)

        # Optional outputs
        ctk.CTkLabel(frm, text="Out CSV").grid(
            row=1, column=0, sticky="w", padx=6, pady=6
        )
        self.segm_csv = ctk.CTkEntry(frm, width=620)
        self.segm_csv.grid(row=1, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm,
            text="Save As",
            command=lambda: self._pick_save(
                self.segm_csv, defext=".csv", ftypes=[("CSV", "*.csv")]
            ),
        ).grid(row=1, column=2, padx=6, pady=6)

        ctk.CTkLabel(frm, text="Out CUE").grid(
            row=2, column=0, sticky="w", padx=6, pady=6
        )
        self.segm_cue = ctk.CTkEntry(frm, width=620)
        self.segm_cue.grid(row=2, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm,
            text="Save As",
            command=lambda: self._pick_save(
                self.segm_cue, defext=".cue", ftypes=[("CUE sheet", "*.cue")]
            ),
        ).grid(row=2, column=2, padx=6, pady=6)

        ctk.CTkLabel(frm, text="Plot HTML").grid(
            row=3, column=0, sticky="w", padx=6, pady=6
        )
        self.segm_html = ctk.CTkEntry(frm, width=620)
        self.segm_html.grid(row=3, column=1, sticky="we", padx=6, pady=6)
        ctk.CTkButton(
            frm,
            text="Save As",
            command=lambda: self._pick_save(
                self.segm_html, defext=".html", ftypes=[("HTML", "*.html")]
            ),
        ).grid(row=3, column=2, padx=6, pady=6)

        frm.grid_columnconfigure(1, weight=1)

        self.segm_run_btn = ctk.CTkButton(
            self.segm_tab, text="Run Segmenter", command=self._run_segmenter
        )
        self.segm_run_btn.pack(padx=12, pady=(0, 8))

        self.segm_log = ctk.CTkTextbox(self.segm_tab, height=360)
        self.segm_log.pack(fill="both", expand=True, padx=12, pady=8)
        self.segm_runner = Runner(self.segm_log, self.segm_run_btn)

    def _run_segmenter(self):
        audio = self.audio_path.get().strip()
        if not os.path.isfile(audio):
            messagebox.showerror("Missing audio", "Please choose a valid audio file.")
            return

        seg_py = os.path.join(SRC_DIR, "mixtape_segmenter.py")
        if not os.path.isfile(seg_py):
            messagebox.showerror("Not found", f"Could not find {seg_py}")
            return

        cmd = (
            f"{shlex.quote(which_python())} {shlex.quote(seg_py)} {shlex.quote(audio)}"
        )
        if self.segm_csv.get().strip():
            cmd += f" --out-csv {shlex.quote(self.segm_csv.get().strip())}"
        if self.segm_cue.get().strip():
            cmd += f" --out-cue {shlex.quote(self.segm_cue.get().strip())}"
        if self.segm_html.get().strip():
            cmd += f" --plot-html {shlex.quote(self.segm_html.get().strip())}"

        self.segm_runner.run_async(cmd, cwd=SRC_DIR)

    # ---------- Generic "Scripts" tab ----------
    def _build_scripts_tab(self):
        top = ctk.CTkFrame(self.scripts_tab)
        top.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(top, text="Script").grid(
            row=0, column=0, sticky="w", padx=6, pady=6
        )
        self.script_list = ctk.CTkOptionMenu(top, values=discover_scripts())
        vals = discover_scripts()
        if vals:
            self.script_list.set(vals[0])
        self.script_list.grid(row=0, column=1, sticky="we", padx=6, pady=6)

        # Args entry
        ctk.CTkLabel(top, text="Arguments").grid(
            row=1, column=0, sticky="w", padx=6, pady=6
        )
        self.args_entry = ctk.CTkEntry(top, width=700)
        self.args_entry.grid(row=1, column=1, sticky="we", padx=6, pady=6, columnspan=3)

        # Helpers to insert file/dir paths into args
        ctk.CTkButton(
            top,
            text="Insert File…",
            command=lambda: self._insert_path(self.args_entry, file=True),
        ).grid(row=0, column=2, padx=6, pady=6)
        ctk.CTkButton(
            top,
            text="Insert Folder…",
            command=lambda: self._insert_path(self.args_entry, file=False),
        ).grid(row=0, column=3, padx=6, pady=6)

        top.grid_columnconfigure(1, weight=1)

        # Presets row (quick fill for common scripts)
        presets = ctk.CTkFrame(self.scripts_tab)
        presets.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(presets, text="Presets:").grid(
            row=0, column=0, padx=6, pady=6, sticky="w"
        )
        ctk.CTkButton(
            presets, text="metadata.py", command=lambda: self._preset_metadata()
        ).grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkButton(
            presets,
            text="mixtape_segmenter.py",
            command=lambda: self._preset_segmenter(),
        ).grid(row=0, column=2, padx=6, pady=6)
        # Add buttons for your other scripts as generic presets
        for idx, name in enumerate(
            ["enrichedmetadata.py", "highdgraph.py", "highdgraphv2.py", "link2mp3.py"]
        ):
            ctk.CTkButton(
                presets, text=name, command=lambda n=name: self._preset_generic(n)
            ).grid(row=0, column=3 + idx, padx=6, pady=6)

        # Run + Log
        self.generic_run_btn = ctk.CTkButton(
            self.scripts_tab, text="Run Selected Script", command=self._run_generic
        )
        self.generic_run_btn.pack(padx=12, pady=(0, 8))

        self.generic_log = ctk.CTkTextbox(self.scripts_tab, height=360)
        self.generic_log.pack(fill="both", expand=True, padx=12, pady=8)
        self.generic_runner = Runner(self.generic_log, self.generic_run_btn)

    def _preset_metadata(self):
        self.script_list.set("metadata.py")
        # Example: --input <csv> --output <file_or_dir> [--region US] [--use-yt-dlp]
        self.args_entry.delete(0, "end")
        self.args_entry.insert(
            0,
            '--input "<path_to_input.csv>" --output "../csv/" --region US --use-yt-dlp',
        )

    def _preset_segmenter(self):
        self.script_list.set("mixtape_segmenter.py")
        # Example: <audio> [--out-csv out.csv] [--out-cue out.cue] [--plot-html out.html]
        self.args_entry.delete(0, "end")
        self.args_entry.insert(
            0,
            '"../mp3music/example.mp3" --out-csv "segments.csv" --out-cue "segments.cue" --plot-html "segments.html"',
        )

    def _preset_generic(self, script_name):
        self.script_list.set(script_name)
        self.args_entry.delete(0, "end")
        self.args_entry.insert(0, "# enter positional args and --flags here")

    def _run_generic(self):
        script = self.script_list.get().strip()
        if not script:
            messagebox.showerror("No script", "Pick a script to run.")
            return
        script_path = os.path.join(SRC_DIR, script)
        if not os.path.isfile(script_path):
            messagebox.showerror("Not found", f"Could not find {script_path}")
            return

        args = self.args_entry.get().strip()
        cmd = f"{shlex.quote(which_python())} {shlex.quote(script_path)}"
        if args:
            cmd += f" {args}"

        self.generic_runner.run_async(cmd, cwd=SRC_DIR)

    # ---------- pickers ----------
    def _pick_file(self, entry, ftypes):
        path = filedialog.askopenfilename(filetypes=ftypes)
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _pick_save(self, entry, defext="", ftypes=None):
        path = filedialog.asksaveasfilename(
            defaultextension=defext, filetypes=ftypes or [("All files", "*.*")]
        )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _pick_save_or_dir(self, entry):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv"), ("All files", "*.*")]
        )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)
            return
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, "end")
            entry.insert(0, d + os.sep)

    def _insert_path(self, entry, file=True):
        if file:
            p = filedialog.askopenfilename()
        else:
            p = filedialog.askdirectory()
        if p:
            # append with quotes (safe for spaces)
            cur = entry.get()
            add = f' "{p}"'
            entry.delete(0, "end")
            entry.insert(0, (cur + add).strip())


if __name__ == "__main__":
    # Ensure src exists
    if not os.path.isdir(SRC_DIR):
        messagebox.showerror("Missing src", f"Couldn't find src folder at:\n{SRC_DIR}")
        sys.exit(1)
    App().mainloop()
