#!/usr/bin/env python3
"""Sokak GPS Ayirici - masaustu programi (Tkinter).

sirala.py'deki OCR/EXIF/klasorleme mantigini kullanarak, kaynak ve hedef
klasor secmenizi saglayan basit bir pencere sunar. Ekstra kurulum
gerektirmez (Tkinter Python ile birlikte gelir); sadece requirements.txt
ve Tesseract OCR kurulu olmali (bkz. README.md).

Iki sekme var:
    - "Otomatik Sıralama": OCR ile toplu isleme (asil program).
    - "Elle GPS Ekle": OCR'in okuyamadigi (Bulunamayanlar) fotograflar icin
      Lat/Long'u elle girip toplu disa aktarma.
"""

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sirala

MANUAL_EXPORT_FOLDER = "BulunamayanlarExport"


class AutoSortTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
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

    def _prompt_manual_tesseract(self) -> bool:
        """Tesseract otomatik bulunamadiginda, kullaniciya tesseract.exe'yi elle
        secme secenegi sunar. Basariliysa True doner ve konumu bir dahaki
        acilista tekrar sormamak icin kaydeder."""
        if not messagebox.askyesno(
            "Tesseract bulunamadı",
            "Tesseract OCR otomatik olarak bulunamadı.\n\n"
            "Eğer Tesseract'ı kurduysanız, tesseract.exe dosyasının konumunu "
            "elle seçmek ister misiniz?\n\n"
            "(Kurmadıysanız 'Hayır'a basıp önce "
            "https://github.com/UB-Mannheim/tesseract/wiki adresinden kurun.)",
        ):
            return False
        path = filedialog.askopenfilename(
            title="tesseract.exe dosyasını seçin",
            filetypes=[("tesseract.exe", "tesseract.exe"), ("Tüm dosyalar", "*.*")],
        )
        if not path:
            return False
        sirala.pytesseract.pytesseract.tesseract_cmd = path
        try:
            sirala.pytesseract.get_tesseract_version()
        except Exception:
            messagebox.showerror("Geçersiz dosya", "Seçilen dosya çalışan bir Tesseract programı değil.")
            return False
        sirala.save_tesseract_cmd(path)
        return True

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
            if not self._prompt_manual_tesseract():
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


class ManualGpsTab(ttk.Frame):
    """OCR'in okuyamadigi fotograflar icin Lat/Long'u elle girip GPS yazma araci."""

    def __init__(self, master):
        super().__init__(master)
        self.folder: Path | None = None
        self.files: list[Path] = []
        self.entries: dict[str, tuple[float, float]] = {}
        self._build_widgets()

    def _build_widgets(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="Bulunamayanlar klasörü:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.folder_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Gözat…", command=self._pick_folder).pack(side="left")

        mid = ttk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=6)

        list_frame = ttk.Frame(mid)
        list_frame.pack(side="left", fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, exportselection=False)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        list_scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=list_scroll.set)
        list_scroll.pack(side="right", fill="y")

        form = ttk.Frame(mid)
        form.pack(side="left", fill="y", padx=(12, 0))
        self.selected_label = ttk.Label(form, text="Seçili dosya: -", wraplength=220)
        self.selected_label.pack(anchor="w", pady=(0, 10))
        ttk.Label(form, text="Lat (Enlem):").pack(anchor="w")
        self.lat_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.lat_var, width=22).pack(anchor="w")
        ttk.Label(form, text="Long (Boylam):").pack(anchor="w", pady=(8, 0))
        self.lon_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.lon_var, width=22).pack(anchor="w")
        ttk.Button(form, text="Bu Fotoğrafı Kaydet", command=self._save_current).pack(anchor="w", pady=14)
        ttk.Label(form, text="(✓ işaretli olanlar\nzaten girildi)", foreground="#666").pack(anchor="w")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 4))
        self.export_btn = ttk.Button(
            bottom, text=f"Tümünü Dışa Aktar ({MANUAL_EXPORT_FOLDER})", command=self._export_all
        )
        self.export_btn.pack(side="left")
        self.status_label = ttk.Label(bottom, text="")
        self.status_label.pack(side="left", padx=10)

        self.log_text = tk.Text(self, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=False, padx=10, pady=(6, 10))

    def _append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _pick_folder(self):
        path = filedialog.askdirectory(title="Bulunamayanlar klasörünü seçin")
        if not path:
            return
        self.folder_var.set(path)
        self.folder = Path(path)
        self.files = list(sirala.iter_image_files(self.folder))
        self.entries.clear()
        self._refresh_list()
        self.lat_var.set("")
        self.lon_var.set("")
        self.selected_label.configure(text="Seçili dosya: -")

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for path in self.files:
            mark = "✓ " if path.name in self.entries else "   "
            self.listbox.insert("end", f"{mark}{path.name}")

    def _on_select(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return
        path = self.files[selection[0]]
        self.selected_label.configure(text=f"Seçili dosya: {path.name}")
        if path.name in self.entries:
            lat, lon = self.entries[path.name]
            self.lat_var.set(str(lat))
            self.lon_var.set(str(lon))
        else:
            self.lat_var.set("")
            self.lon_var.set("")

    def _save_current(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showwarning("Fotoğraf seçilmedi", "Önce listeden bir fotoğraf seçin.")
            return
        path = self.files[selection[0]]
        try:
            lat = float(self.lat_var.get().strip().replace(",", "."))
            lon = float(self.lon_var.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Geçersiz değer", "Lat ve Long için geçerli bir sayı girin (örn. 51.357283).")
            return
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            messagebox.showerror("Geçersiz değer", "Lat -90..90, Long -180..180 aralığında olmalı.")
            return
        self.entries[path.name] = (lat, lon)
        self._refresh_list()
        for i, p in enumerate(self.files):
            if p == path:
                self.listbox.selection_set(i)
                break
        self._append_log(f"Kaydedildi: {path.name} -> {lat}, {lon}")

    def _export_all(self):
        if not self.entries:
            messagebox.showwarning("Boş liste", "Henüz hiçbir fotoğraf için Lat/Long girmediniz.")
            return
        if self.folder is None:
            return
        dest_dir = self.folder / MANUAL_EXPORT_FOLDER
        dest_dir.mkdir(parents=True, exist_ok=True)
        ok, failed = 0, 0
        for path in self.files:
            if path.name not in self.entries:
                continue
            lat, lon = self.entries[path.name]
            try:
                dest_path = sirala.unique_dest(dest_dir / path.name)
                sirala.save_with_gps(path, dest_path, lat, lon)
                ok += 1
                self._append_log(f"Dışa aktarıldı: {path.name}")
            except Exception as exc:
                failed += 1
                self._append_log(f"HATA ({path.name}): {exc}")
        self.status_label.configure(text=f"{ok} fotoğraf dışa aktarıldı" + (f", {failed} hata" if failed else ""))
        messagebox.showinfo(
            "Bitti",
            f"{ok} fotoğraf GPS'lenip '{MANUAL_EXPORT_FOLDER}' klasörüne kaydedildi."
            + (f"\n{failed} fotoğrafta hata oluştu." if failed else ""),
        )


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sokak GPS Ayırıcı")
        self.geometry("820x600")
        self.minsize(680, 480)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)
        notebook.add(AutoSortTab(notebook), text="Otomatik Sıralama")
        notebook.add(ManualGpsTab(notebook), text="Elle GPS Ekle")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
