#!/usr/bin/env python3
"""Sokak GPS Ayirici - masaustu programi (Tkinter).

sirala.py'deki OCR/EXIF/klasorleme mantigini kullanarak, kaynak ve hedef
klasor secmenizi saglayan basit bir pencere sunar. Ekstra kurulum
gerektirmez (Tkinter Python ile birlikte gelir); sadece requirements.txt
ve Tesseract OCR kurulu olmali (bkz. README.md).
"""

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sirala


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sokak GPS Ayırıcı")
        self.geometry("760x560")
        self.minsize(620, 440)

        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.move_var = tk.BooleanVar(value=False)
        self.msg_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        self._build_widgets()
        self.after(100, self._poll_queue)

    def _build_widgets(self):
        pad = {"padx": 10, "pady": 6}

        frm_top = ttk.Frame(self)
        frm_top.pack(fill="x", **pad)

        ttk.Label(frm_top, text="Kaynak klasör (fotoğraflar):").grid(row=0, column=0, sticky="w")
        ttk.Entry(frm_top, textvariable=self.source_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frm_top, text="Gözat…", command=self._pick_source).grid(row=1, column=1)

        ttk.Label(frm_top, text="Hedef klasör (sokak klasörleri buraya oluşturulacak):").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Entry(frm_top, textvariable=self.dest_var).grid(row=3, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frm_top, text="Gözat…", command=self._pick_dest).grid(row=3, column=1)

        frm_top.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            frm_top,
            text="Kopyalamak yerine kaynaktan taşı (işlenen dosyalar kaynaktan silinir)",
            variable=self.move_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        frm_btn = ttk.Frame(self)
        frm_btn.pack(fill="x", **pad)
        self.start_btn = ttk.Button(frm_btn, text="Başlat", command=self._start)
        self.start_btn.pack(side="left")
        self.progress = ttk.Progressbar(frm_btn, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.progress_label = ttk.Label(frm_btn, text="")
        self.progress_label.pack(side="left")

        frm_log = ttk.Frame(self)
        frm_log.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(frm_log, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(frm_log, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _pick_source(self):
        path = filedialog.askdirectory(title="Kaynak klasörü seçin")
        if path:
            self.source_var.set(path)

    def _pick_dest(self):
        path = filedialog.askdirectory(title="Hedef klasörü seçin")
        if path:
            self.dest_var.set(path)

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    i, total = payload
                    self.progress["maximum"] = total
                    self.progress["value"] = i
                    self.progress_label.configure(text=f"{i}/{total}")
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    if payload:
                        messagebox.showerror("Hata", payload)
                    else:
                        messagebox.showinfo("Bitti", "İşlem tamamlandı. Ayrıntılar için günlüğe ve islem_log.csv dosyasına bakın.")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _start(self):
        source = self.source_var.get().strip()
        dest = self.dest_var.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showwarning("Eksik bilgi", "Geçerli bir kaynak klasör seçin.")
            return
        if not dest:
            messagebox.showwarning("Eksik bilgi", "Hedef klasör seçin.")
            return
        try:
            sirala.pytesseract.get_tesseract_version()
        except Exception:
            messagebox.showerror(
                "Tesseract bulunamadı",
                "Tesseract OCR kurulu değil veya PATH'te değil.\n\n"
                "Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
                "macOS: brew install tesseract tesseract-lang\n"
                "Linux: sudo apt install tesseract-ocr tesseract-ocr-deu",
            )
            return

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.progress["value"] = 0
        self.progress_label.configure(text="")
        self.start_btn.configure(state="disabled")

        self.worker = threading.Thread(
            target=self._run_worker, args=(Path(source), Path(dest), self.move_var.get()), daemon=True
        )
        self.worker.start()

    def _run_worker(self, source: Path, dest: Path, move: bool):
        def log(text):
            self.msg_queue.put(("log", str(text)))

        def on_progress(i, total):
            self.msg_queue.put(("progress", (i, total)))

        try:
            lang = sirala.detect_ocr_lang()
            sirala.process(source, dest, lang, move, log=log, on_progress=on_progress)
            self.msg_queue.put(("done", None))
        except Exception as exc:
            log(f"Beklenmeyen hata: {exc}")
            self.msg_queue.put(("done", str(exc)))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
