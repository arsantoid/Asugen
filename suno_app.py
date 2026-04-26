# ═══════════════════════════════════════════════════════════════════
#  suno_app.py  —  ASuGen v5.39  (ENTRY POINT)
#  ASuGen — AppV2 UI + main block
#  Jalankan: python suno_app.py
# ═══════════════════════════════════════════════════════════════════
from suno_dialogs import *
# FIX: import eksplisit semua fungsi/variable prefix _ dari suno_core
from suno_core import (
    _stop_requested, _run_async, _minimize_chrome_windows,
    _prompt_to_folder_name, _get_profile_abs, _save_profiles_raw,
    get_stop_event, request_stop, clear_stop, is_stop_requested,
    request_pause, resume_generate, is_paused, wait_if_paused,
    save_window_position, load_window_position
)

class AppV2(tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.title("ASuGen v5.39")
        self.geometry("1360x820")
        self.minsize(1220, 720)
        _app_cfg = load_app_config()
        _saved_chrome = _app_cfg.get("chrome_path", "")
        _chrome_init = _saved_chrome if (_saved_chrome and os.path.exists(_saved_chrome)) else (find_chrome() or "")
        self.chrome_path_var = tk.StringVar(value=_chrome_init)
        self.headless_var = tk.BooleanVar(value=_app_cfg.get("headless", False))
        self.status_var = tk.StringVar(value="Ready")
        self.profiles = load_profiles()
        self._generate_running = False
        self._build_ui()
        self.refresh_table()
        self._init_log_file()
        self.chrome_path_var.trace_add("write", self._on_chrome_path_change)


    @staticmethod
    def _pdir(p: dict) -> str:
        """Resolve profile_dir ke absolute path. Portable meski folder dipindah."""
        cached = p.get("_profile_dir_abs")
        if cached:
            return cached
        abs_path = resolve_profile_dir(p.get("profile_dir", ""))
        p["_profile_dir_abs"] = abs_path  # cache untuk session ini
        return abs_path

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        top = ttk.LabelFrame(root, text="Chrome")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(top, text="Chrome Path").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ttk.Entry(top, textvariable=self.chrome_path_var, width=110).grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        ttk.Button(top, text="📂 Browse", command=self.browse_chrome).grid(row=0, column=2, padx=4, pady=8)
        ttk.Button(top, text="🔍 Detect & Save", command=self.detect_chrome).grid(row=0, column=3, padx=4, pady=8)
        top.columnconfigure(1, weight=1)

        main_pane = ttk.Panedwindow(root, orient=tk.VERTICAL)
        main_pane.grid(row=1, column=0, sticky="nsew")

        upper = ttk.Frame(main_pane)
        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(0, weight=1)
        main_pane.add(upper, weight=4)

        lower = ttk.Frame(main_pane)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(0, weight=1)
        main_pane.add(lower, weight=2)

        content_pane = ttk.Panedwindow(upper, orient=tk.HORIZONTAL)
        content_pane.grid(row=0, column=0, sticky="nsew")

        left = ttk.LabelFrame(content_pane, text="Profiles")
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        content_pane.add(left, weight=5)

        cols = ("name", "email", "credits", "status", "status_info", "profile_dir")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=15, selectmode="extended")
        self.tree.heading("name",        text="Name")
        self.tree.heading("email",       text="Email / Note")
        self.tree.heading("credits",     text="Kredit")
        self.tree.heading("status",      text="Tipe")
        self.tree.heading("status_info", text="Status Terkini")
        self.tree.heading("profile_dir", text="Profile Folder")
        self.tree.column("name",        width=160)
        self.tree.column("email",       width=175)
        self.tree.column("credits",     width=80,  anchor="center")
        self.tree.column("status",      width=75,  anchor="center")
        self.tree.column("status_info", width=160, anchor="w")
        self.tree.column("profile_dir", width=270)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(4, 0))
        tree_sb = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_sb.set)
        tree_sb.grid(row=0, column=1, sticky="ns", pady=(4, 0))

        # ── Klik kanan tabel → context menu ──────────────────────────────────
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="🎵  Generate Single",    command=self._ctx_generate_single)
        self._ctx_menu.add_command(label="⚡  Generate Bulk",       command=self._ctx_generate_bulk)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="⬇️  Download Lagu",       command=self._ctx_download)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="💰  Cek Kredit",          command=self._ctx_cek_kredit)
        self._ctx_menu.add_command(label="💰  Cek Kredit Semua",    command=self._ctx_cek_kredit_semua)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="🌐  Buka Chrome Profile", command=self._ctx_open_browser)
        self._ctx_menu.add_command(label="📁  Buka Folder Profile", command=self._ctx_open_folder)
        self._ctx_menu.add_command(label="⭐  Toggle Premium",      command=self._ctx_toggle_premium)
        self._ctx_menu.add_command(label="✏️  Rename Profile",       command=self._ctx_rename)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="⏹  Stop Generate",       command=self._ctx_stop)
        self._ctx_menu.add_command(label="🗑️  Hapus Profile",        command=self._ctx_delete)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        self.summary_var = tk.StringVar(value="Total bisa create: 0")
        ttk.Label(left, textvariable=self.summary_var, anchor="w").grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 6))

        right = ttk.LabelFrame(content_pane, text="Actions")
        content_pane.add(right, weight=1)

        for text_btn, cmd in [
            ("Add Profile", self.add_account),
            ("Open Selected", self.open_selected),
            ("Open Profile Folder", self.open_profile_folder),
            ("Rename Selected", self.rename_selected),
            ("Delete Selected", self.delete_selected),
            ("Refresh", self.refresh_table),
        ]:
            ttk.Button(right, text=text_btn, command=cmd, width=24).pack(padx=10, pady=3, fill="x")

        ttk.Separator(right).pack(fill="x", padx=6, pady=6)
        ttk.Button(right, text="⚙️ AI Settings", command=self.open_ai_settings, width=24).pack(padx=10, pady=3, fill="x")
        ttk.Button(right, text="✍ Prompt Manager", command=self.open_prompt_manager, width=24).pack(padx=10, pady=3, fill="x")
        ttk.Button(right, text="⏱ Runtime Settings", command=self.open_runtime_settings, width=24).pack(padx=10, pady=3, fill="x")
        ttk.Button(right, text="Toggle Premium", command=self.toggle_premium, width=24).pack(padx=10, pady=3, fill="x")

        ttk.Separator(right).pack(fill="x", padx=6, pady=6)
        ttk.Button(right, text="💰 Cek Kredit Selected", command=self.cek_kredit_selected, width=24).pack(padx=10, pady=3, fill="x")
        ttk.Button(right, text="💰 Cek Kredit Semua Profile", command=self.cek_kredit_semua, width=24).pack(padx=10, pady=3, fill="x")

        ttk.Separator(right).pack(fill="x", padx=6, pady=6)
        self.buat_btn = ttk.Button(right, text="🎵 Buat Lagu (Selected)", command=self.buat_lagu, width=24)
        self.buat_btn.pack(padx=10, pady=3, fill="x")
        ttk.Button(right, text="🚀 Bulk Create", command=self.bulk_create, width=24).pack(padx=10, pady=3, fill="x")
        self.stop_btn = ttk.Button(right, text="⏹ STOP Generate", command=self.stop_generate, width=24)
        self.stop_btn.pack(padx=10, pady=3, fill="x")
        self.stop_btn.state(["disabled"])

        self.pause_btn = ttk.Button(right, text="⏸ Pause", command=self.toggle_pause, width=24)
        self.pause_btn.pack(padx=10, pady=3, fill="x")
        self.pause_btn.state(["disabled"])
        self._is_paused = False

        ttk.Separator(right).pack(fill="x", padx=6, pady=6)
        ttk.Button(right, text="⬇️ Download Lagu (Selected)", command=self.download_lagu_selected, width=24).pack(padx=10, pady=3, fill="x")

        logf = ttk.LabelFrame(lower, text="Log")
        logf.grid(row=0, column=0, sticky="nsew")
        logf.columnconfigure(0, weight=1)
        logf.rowconfigure(0, weight=1)
        self.log_text = tk.Text(logf, height=12, state="disabled", wrap="word", font=("Consolas", 9))
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)
        sb.grid(row=0, column=1, sticky="ns", pady=4)

        status_bar = ttk.Frame(root)
        status_bar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(status_bar, textvariable=self.status_var, anchor="w").pack(side="left", fill="x", expand=True)

    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status_var.set(text[:100])
        try:
            if getattr(self, "_log_file", None):
                import datetime as _dt
                self._log_file.write(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {text}\n")
                self._log_file.flush()
        except Exception:
            pass

    def _init_log_file(self):
        try:
            import datetime as _dt
            _ld = Path.home() / "suno_downloads" / "logs"
            _ld.mkdir(parents=True, exist_ok=True)
            _fn = _ld / f"asugen_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            self._log_file = open(_fn, "w", encoding="utf-8")
            self._log_file.write(f"=== ASUnoGEn Log — {_dt.datetime.now()} ===\n")
        except Exception:
            self._log_file = None

    def _thread_log(self, msg):
        self.after(0, self.log, msg)

    def _on_chrome_path_change(self, *_):
        path = self.chrome_path_var.get().strip()
        if path:
            cfg = load_app_config()
            cfg["chrome_path"] = path
            save_app_config(cfg)

    def browse_chrome(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Pilih Chrome executable",
            filetypes=[("Chrome executable", "chrome.exe"), ("Semua file", "*.*")],
            initialdir=os.path.expandvars(r"%PROGRAMFILES%"),
        )
        if path and os.path.exists(path):
            self.chrome_path_var.set(path)
            cfg = load_app_config()
            cfg["chrome_path"] = path
            save_app_config(cfg)
            self.log(f"✅ Chrome path disimpan: {path}")

    def detect_chrome(self):
        found = find_chrome()
        if found:
            self.chrome_path_var.set(found)
            cfg = load_app_config()
            cfg["chrome_path"] = found
            save_app_config(cfg)
            self.log(f"✅ Chrome ditemukan & disimpan: {found}")
        else:
            self.log("⚠️ Chrome tidak terdeteksi otomatis. Gunakan tombol Browse untuk pilih manual.")
            messagebox.showwarning(
                "Chrome Tidak Ditemukan",
                "Chrome tidak terdeteksi otomatis.\n\n"
                "Gunakan tombol 'Browse' untuk pilih chrome.exe manual.\n\n"
                "Biasanya di: C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
            )

    def open_ai_settings(self):
        AISettingsDialog(self)

    def open_prompt_manager(self):
        """Buka Prompt Manager — kelola dan pilih custom prompt."""
        from suno_dialogs import PromptManagerDialog
        PromptManagerDialog(self)

    def open_runtime_settings(self):
        RuntimeSettingsDialog(self)
        cfg = load_app_config()
        self.headless_var.set(cfg.get("headless", False))

    def _available(self, prof):
        return get_profile_credit_quota(prof)

    def refresh_table(self):
        self.profiles = load_profiles()
        changed = False
        for p in self.profiles:
            if "is_premium" not in p:
                p["is_premium"] = False
                changed = True
            if "credits_remaining" not in p:
                p["credits_remaining"] = ""
                changed = True
            if "email" not in p:
                p["email"] = ""
                changed = True
            if "create_count" in p:
                p.pop("create_count", None)
                changed = True
            if "counter_date" in p:
                p.pop("counter_date", None)
                changed = True
        if changed:
            save_profiles(self.profiles)

        self.tree.tag_configure("captcha", background="#4a2a00", foreground="#ffcc55")
        self.tree.tag_configure("error",   background="#3a0000", foreground="#ff7070")
        self.tree.tag_configure("done",    background="#003a10", foreground="#80ff99")
        self.tree.tag_configure("running", background="#002540", foreground="#66ccff")
        self.tree.tag_configure("normal",  background="",        foreground="")

        for i in self.tree.get_children():
            self.tree.delete(i)

        total_available = 0
        unknown_count = 0
        premium_count = 0
        for p in self.profiles:
            prem = p.get("is_premium", False)
            credit_num = parse_credit_value(p.get("credits_remaining"))
            credit_label = "Pro" if prem else ("-" if credit_num is None else str(credit_num))
            if prem:
                premium_count += 1
            else:
                total_available += self._available(p)
                if credit_num is None:
                    unknown_count += 1
            _st = p.get("status_info", "")
            if "CAPTCHA" in _st:
                _tag = "captcha"
            elif any(x in _st for x in ["❌", "Error", "Gagal", "Kredit habis"]):
                _tag = "error"
            elif any(x in _st for x in ["✅", "Done", "Selesai"]):
                _tag = "done"
            elif any(x in _st for x in ["⏳", "Running", "Generate"]):
                _tag = "running"
            else:
                _tag = "normal"
            self.tree.insert("", "end", tags=(_tag,), values=(
                p.get("name", ""),
                p.get("email", ""),
                credit_label,
                "Pro" if prem else "Regular",
                _st,
                p.get("profile_dir", ""),
            ))
        summary = f"Total bisa create (free): {total_available}"
        if premium_count:
            summary += f" | Premium: {premium_count} profile (skip cek kredit)"
        if unknown_count:
            summary += f" | Belum dicek: {unknown_count} profile"
        self.summary_var.set(summary)
        self.log(f"{len(self.profiles)} profile(s). {summary}")

    def _find_by_dir(self, d):
        """Cari profile by dir — support slug relatif maupun path absolut lama."""
        if not d:
            return None
        d_slug = Path(d).name
        for p in self.profiles:
            pd = p.get("profile_dir", "")
            if pd == d or Path(pd).name == d_slug or self._pdir(p) == str(Path(d)):
                return p
        return None

    def get_selected_profile(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Warning", "Pilih profile dulu.")
            return None
        vals = self.tree.item(sel[0], "values")
        # Defensive: coba index 5 (6-col) lalu 4 (5-col) untuk backward compat
        for _idx in (5, 4, 3):
            if len(vals) > _idx:
                p = self._find_by_dir(vals[_idx])
                if p:
                    return p
        # Last resort: cari by name
        if vals:
            for p in self.profiles:
                if p.get("name", "") == vals[0]:
                    return p
        messagebox.showwarning("Warning", "Profile tidak ditemukan.")
        return None

    def get_selected_profiles(self):
        out = []
        for iid in self.tree.selection():
            vals = self.tree.item(iid, "values")
            p = None
            for _idx in (5, 4, 3):
                if len(vals) > _idx:
                    p = self._find_by_dir(vals[_idx])
                    if p:
                        break
            if not p and vals:
                for _pr in self.profiles:
                    if _pr.get("name","") == vals[0]:
                        p = _pr; break
            if p:
                out.append(p)
        if not out:
            messagebox.showwarning("Warning", "Pilih minimal 1 profile.")
        return out

    def add_account(self):
        dlg = AddProfileDialog(self, "Add Profile")
        if dlg.result is None:
            return

        name = dlg.result["name"]
        email = dlg.result.get("email", "")
        slug = slugify(name)
        pd = DATA_DIR / slug
        i = 2
        while pd.exists():
            pd = DATA_DIR / f"{slug}_{i}"
            i += 1
        pd.mkdir(parents=True, exist_ok=True)
        self.profiles.append({
            "name": name.strip(),
            "email": email.strip(),
            "profile_dir": pd.name,          # FIX: simpan slug relatif agar portable
            "is_premium": False,
            "credits_remaining": "",
        })
        save_profiles(self.profiles)
        self.refresh_table()
        self.log(f"Added profile: {name}")

    def rename_selected(self):
        p = self.get_selected_profile()
        if not p:
            return
        n = simpledialog.askstring("Rename", "Profile (nama + email):", initialvalue=p.get("name", ""))
        if n:
            p["name"] = n.strip()
            save_profiles(self.profiles)
            self.refresh_table()

    def delete_selected(self):
        p = self.get_selected_profile()
        if not p:
            return
        if not messagebox.askyesno("Delete", f"Hapus '{p['name']}'?"):
            return
        try:
            shutil.rmtree(Path(self._pdir(p)), ignore_errors=True)
        except Exception:
            pass
        self.profiles = [x for x in self.profiles if x.get("profile_dir") != p.get("profile_dir")]
        save_profiles(self.profiles)
        self.refresh_table()

    def toggle_premium(self):
        p = self.get_selected_profile()
        if not p:
            return
        p["is_premium"] = not p.get("is_premium", False)
        save_profiles(self.profiles)
        self.refresh_table()

    def open_selected(self):
        p = self.get_selected_profile()
        if not p:
            return
        chrome = self.chrome_path_var.get().strip()
        if not chrome or not os.path.exists(chrome):
            if messagebox.askyesno("Chrome Tidak Ditemukan",
                "Chrome path belum diset atau tidak valid.\n\n"
                "Klik YES untuk Browse dan pilih chrome.exe sekarang,\n"
                "atau NO untuk batalkan aksi ini."):
                self.browse_chrome()
                chrome = self.chrome_path_var.get().strip()
                if not chrome or not os.path.exists(chrome):
                    return
            else:
                return
        subprocess.Popen([chrome, f'--user-data-dir={self._pdir(p)}', "--no-first-run", "--no-default-browser-check", SUNO_URL])

    def open_profile_folder(self):
        p = self.get_selected_profile()
        if p:
            os.startfile(str(Path(self._pdir(p))))

    def _check_playwright(self):
        try:
            import playwright  # noqa
            return True
        except ImportError:
            messagebox.showerror("Playwright", "Jalankan:\npip install playwright\nplaywright install chromium")
            return False

    def stop_generate(self):
        if self._generate_running:
            request_stop()    # FIX: thread-safe helper dari suno_core
            self.log("[STOP] Stop diminta — menunggu lagu saat ini selesai...")
            self.stop_btn.state(["disabled"])
            if self._is_paused:
                self._is_paused = False
                self.pause_btn.config(text="⏸ Pause")
                self.pause_btn.state(["disabled"])

    def toggle_pause(self):
        """Pause/Resume automation tanpa menutup Chrome."""
        if not self._generate_running:
            return
        if not self._is_paused:
            self._is_paused = True
            request_pause()
            self.pause_btn.config(text="▶ Lanjutkan")
            self.log("[⏸ PAUSE] Dijeda setelah lagu ini — Chrome tetap buka.")
        else:
            self._is_paused = False
            resume_generate()
            self.pause_btn.config(text="⏸ Pause")
            self.log("[▶ LANJUT] Automation dilanjutkan.")

    def _set_credit_result(self, profile_dir: str, credits_raw):
        p = self._find_by_dir(profile_dir)
        if not p:
            return
        value = parse_credit_value(credits_raw)
        if value is None:
            p["status_info"] = "⚠ Gagal cek kredit"
            save_profiles(self.profiles)
            self.after(0, self.refresh_table)
            self.after(0, self.log, f"[KREDIT] {p['name']} -> ⚠ Gagal baca kredit (browser error/timeout)")
            return
        p["credits_remaining"] = value
        p.pop("status_info", None)
        save_profiles(self.profiles)
        self.after(0, self.refresh_table)
        self.after(0, self.log, f"[KREDIT] {p['name']} -> {value} kredit | bisa create: {get_profile_credit_quota(p)}")
        try:
            import csv, datetime as _dt
            _csv_dir = Path.home() / "suno_downloads" / "logs"
            _csv_dir.mkdir(parents=True, exist_ok=True)
            _csv_path = _csv_dir / "credit_history.csv"
            _is_new = not _csv_path.exists()
            with open(_csv_path, "a", newline="", encoding="utf-8") as _cf:
                _cw = csv.writer(_cf)
                if _is_new:
                    _cw.writerow(["datetime", "profile", "email", "credits"])
                _cw.writerow([_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              p.get("name",""), p.get("email", p.get("name","")), value])
        except Exception:
            pass

    def _run_credit_check_for_profiles(self, profiles):
        chrome = self.chrome_path_var.get().strip()
        if not chrome or not os.path.exists(chrome):
            if messagebox.askyesno("Chrome Tidak Ditemukan",
                "Chrome path belum diset atau tidak valid.\n\n"
                "Klik YES untuk Browse dan pilih chrome.exe sekarang,\n"
                "atau NO untuk batalkan aksi ini."):
                self.browse_chrome()
                chrome = self.chrome_path_var.get().strip()
                if not chrome or not os.path.exists(chrome):
                    return
            else:
                return
        if not self._check_playwright():
            return

        # Guard: cegah multiple thread cek kredit berjalan bersamaan
        if getattr(self, "_credit_check_running", False):
            self._thread_log("[KREDIT] ⚠ Cek kredit sedang berjalan, tunggu selesai dulu.")
            return
        self._credit_check_running = True

        def worker():
            try:
                non_premium = [p for p in profiles if not p.get("is_premium", False)]
                skipped = len(profiles) - len(non_premium)
                if skipped:
                    self._thread_log(f"[KREDIT] Skip {skipped} akun premium.")
                if not non_premium:
                    self._thread_log("[KREDIT] Semua profile yang dipilih adalah premium, tidak ada yang dicek.")
                    self.after(0, self.refresh_table)
                    return
                for idx, p in enumerate(non_premium, 1):
                    if is_stop_requested():
                        break
                    self._thread_log(f"[KREDIT] ({idx}/{len(non_premium)}) Cek {p['name']}...")
                    run_check_credits(
                        chrome,
                        self._pdir(p),
                        self._thread_log,
                        lambda credits, pd=self._pdir(p): self._set_credit_result(pd, credits),
                        True,
                    )
                self._thread_log("[KREDIT] Selesai cek kredit.")
                self.after(0, self.refresh_table)
            finally:
                self._credit_check_running = False  # selalu reset meski error

        threading.Thread(target=worker, daemon=True).start()

    def cek_kredit_selected(self, force_profile=None):
        if force_profile is not None:
            self._run_credit_check_for_profiles([force_profile])
            return
        profiles = self.get_selected_profiles()
        if profiles:
            self._run_credit_check_for_profiles(profiles)

    def cek_kredit_semua(self):
        if not self.profiles:
            messagebox.showwarning("Warning", "Belum ada profile.")
            return
        self._run_credit_check_for_profiles(self.profiles)

    # ── Context menu handlers ────────────────────────────────────────────────
    def _on_tree_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self._ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_generate_single(self):    self.buat_lagu()
    def _ctx_generate_bulk(self):      self.bulk_create()
    def _ctx_download(self):           self.download_lagu_selected()
    def _ctx_cek_kredit(self):         self.cek_kredit_selected()
    def _ctx_cek_kredit_semua(self):   self.cek_kredit_semua()
    def _ctx_open_browser(self):       self.open_selected()
    def _ctx_open_folder(self):        self.open_profile_folder()
    def _ctx_toggle_premium(self):     self.toggle_premium()
    def _ctx_rename(self):             self.rename_selected()
    def _ctx_stop(self):               self.stop_generate()
    def _ctx_delete(self):             self.delete_selected()

    def buat_lagu(self):
        p = self.get_selected_profile()
        if not p:
            return
        chrome = self.chrome_path_var.get().strip()
        if not chrome or not os.path.exists(chrome):
            if messagebox.askyesno("Chrome Tidak Ditemukan",
                "Chrome path belum diset atau tidak valid.\n\n"
                "Klik YES untuk Browse dan pilih chrome.exe sekarang,\n"
                "atau NO untuk batalkan aksi ini."):
                self.browse_chrome()
                chrome = self.chrome_path_var.get().strip()
                if not chrome or not os.path.exists(chrome):
                    return
            else:
                return
        if not self._check_playwright():
            return

        # --- AUTO CEK KREDIT jika belum pernah dicek (credits_remaining kosong) ---
        if not p.get("is_premium", False):
            cr = parse_credit_value(p.get("credits_remaining"))
            if cr is None:
                self.log(f"[AUTO-CEK] Kredit '{p['name']}' belum dicek. Auto cek sekarang...")
                self.status_var.set("Auto cek kredit... harap tunggu")
                self.update()

                import threading as _th
                done_event = _th.Event()
                result_holder = [None]

                def _on_result(credits):
                    result_holder[0] = credits
                    done_event.set()

                def _check_worker():
                    run_check_credits(chrome, self._pdir(p), lambda m: None, _on_result, True)

                t = _th.Thread(target=_check_worker, daemon=True)
                t.start()
                t.join(timeout=60)

                if result_holder[0] is not None:
                    p["credits_remaining"] = result_holder[0]
                    save_profiles(self.profiles)
                    self.refresh_table()
                    self.log(f"[AUTO-CEK] {p['name']} -> {result_holder[0]} kredit")
                else:
                    self.log(f"[AUTO-CEK] Gagal baca kredit '{p['name']}'. Lanjut dengan data yang ada.")

        # Hitung quota
        rem  = self._available(p)                          # berdasarkan MAX_CREATES
        mfc  = get_profile_max_from_credits(p)             # berdasarkan kredit real (tanpa cap)

        if rem <= 0 and mfc <= 0:
            messagebox.showwarning("Kredit", "Profile ini tidak punya kredit tersisa.")
            return

        # Buka dialog — kirim max_from_credits agar tombol Habiskan Semua muncul jika perlu
        dlg = GenerateDialog(self, p['name'], rem, max_from_credits=mfc)
        if dlg.result is None:
            return
        qty = int(dlg.result.get("quantity", 1))
        m = re.search(r"#jumlah\s*=\s*(\d+)", dlg.result.get("description", ""), re.IGNORECASE)
        if m:
            qty = max(1, int(m.group(1)))

        # Validasi: qty tidak boleh melebihi kredit real
        if qty > mfc and not p.get("is_premium", False):
            messagebox.showwarning("Kredit", f"Kamu minta {qty} lagu, tapi kredit hanya cukup untuk {mfc} lagu.")
            return
        dlg.result["quantity"] = qty

        clear_stop()   # FIX: clear via helper dari suno_core
        self._generate_running = True
        self._is_paused = False
        self.buat_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.pause_btn.state(["!disabled"])

        songs_done = [0]

        def on_done():
            songs_done[0] += 1
            self.after(0, self.log, f"[CREATE] {p['name']} -> lagu ke-{songs_done[0]}/{qty} selesai di-generate, menunggu download...")

        def on_finish(created_count, downloaded_count, latest_credits):
            # Selalu ambil object terbaru dari self.profiles (bukan closure stale)
            _live = self._find_by_dir(self._pdir(p)) or p
            # Handle CAPTCHA_SKIP
            if latest_credits == "CAPTCHA_SKIP":
                _live["status_info"] = "⚠ CAPTCHA — perlu manual"
                save_profiles(self.profiles)
                self.after(0, self.refresh_table)
                self.after(0, self.log, "=" * 52)
                self.after(0, self.log, f"  ⚠ CAPTCHA — {_live['name']} di-skip!")
                self.after(0, self.log, "  Buka Chrome manual → solve CAPTCHA → coba lagi.")
                self.after(0, self.log, "=" * 52)
                return
            if not _live.get("is_premium", False):
                if latest_credits is not None:
                    _live["credits_remaining"] = latest_credits
                elif created_count > 0:
                    _cur = parse_credit_value(_live.get("credits_remaining"))
                    if _cur is not None:
                        _live["credits_remaining"] = max(0, _cur - (created_count * FREE_CREDITS_PER_CREATE))

            if created_count > 0:
                _ls = ""
                try:
                    _dl_d = Path(load_app_config().get("download_dir",
                                 str(Path.home() / "suno_downloads")))
                    _ff = sorted(_dl_d.rglob("*.mp3"),
                                 key=lambda x: x.stat().st_mtime, reverse=True)
                    if _ff: _ls = f" | 🎵 {_ff[0].stem[:22]}"
                except Exception: pass
                _live["status_info"] = f"✅ Done {created_count} lagu{_ls}"
            else:
                _live["status_info"] = f"❌ Gagal / kredit habis"
            save_profiles(self.profiles)
            self.after(0, self.refresh_table)
            self.after(0, self.log,
                       f"[CREATE FINISH] {_live['name']} -> sukses: {created_count}, "
                       f"kredit: {latest_credits if latest_credits is not None else _live.get('credits_remaining','?')}")


        def worker():
            run_generate(chrome, self._pdir(p), dlg.result, self._thread_log, on_done, on_finish)
            self._generate_running = False
            self.after(0, lambda: self.buat_btn.state(["!disabled"]))
            self.after(0, lambda: self.stop_btn.state(["disabled"]))
            self.after(0, lambda: self.pause_btn.state(["disabled"]))
            self.after(0, lambda: self.pause_btn.config(text="⏸ Pause"))

        p["status_info"] = f"🔄 Running — {qty} lagu"
        save_profiles(self.profiles)
        self.refresh_table()
        threading.Thread(target=worker, daemon=True).start()

    def bulk_create(self):
        """PATCH: Bulk Create — asumsi 50 kredit/profile, tanpa cek kredit dulu.
        Profile yang dipilih user langsung diproses. Jika kredit 0/habis -> skip profile."""
        selected = self.get_selected_profiles()
        if not selected:
            messagebox.showwarning("Pilih Profile",
                "Pilih minimal 1 profile dulu (Select All atau pilih manual).")
            return

        eligible = [p for p in selected if not p.get("is_premium", False)]
        if not eligible:
            eligible = selected

        max_per_profile = ASSUMED_CREDITS_PER_PROFILE // FREE_CREDITS_PER_CREATE  # 5
        total_assumed   = len(eligible) * max_per_profile

        dlg = BulkCreateDialog(self, eligible, total_assumed)
        if dlg.result is None:
            return

        desc         = dlg.result.get("description", "").strip()
        total        = int(dlg.result.get("quantity", 1))
        instrumental = bool(dlg.result.get("instrumental", False))

        m = re.search(r"#jumlah\s*=\s*(\d+)", desc, re.IGNORECASE)
        if m:
            total = max(1, int(m.group(1)))

        chrome = self.chrome_path_var.get().strip()
        if not chrome or not os.path.exists(chrome):
            if messagebox.askyesno("Chrome Tidak Ditemukan",
                "Chrome path belum diset.\n\nKlik YES untuk Browse chrome.exe, atau NO untuk batal."):
                self.browse_chrome()
                chrome = self.chrome_path_var.get().strip()
                if not chrome or not os.path.exists(chrome):
                    return
            else:
                return
        if not self._check_playwright():
            return

        plan, remain = [], total
        for p in eligible:
            if remain <= 0: break
            take = min(remain, max_per_profile)
            if take > 0:
                plan.append((p, take))
                remain -= take

        if remain > 0:
            self.log(f"[BULK] {remain} lagu tidak terdistribusi — tambah profile atau kurangi jumlah.")

        plan_lines = "\n".join(
            f"  - {p.get('name','-')}: {t} lagu (asumsi 50 kredit, tanpa cek awal)"
            for p, t in plan)
        self.log(f"[BULK PLAN] {total} lagu | {len(plan)} profile\n" + plan_lines)

        clear_stop()   # FIX: clear via helper dari suno_core
        self._generate_running = True
        self.buat_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])

        def worker():
            remain_local = total
            captcha_profiles = []
            for p, take in plan:
                if remain_local <= 0 or is_stop_requested():
                    break
                # Ambil object terbaru dari self.profiles
                _lp = self._find_by_dir(self._pdir(p)) or p
                _lp["status_info"] = f"🔄 Running — {take} lagu"
                save_profiles(self.profiles)
                self.after(0, self.refresh_table)
                self._thread_log(
                    f"[BULK] Profile: {p['name']} -> target {take} lagu (asumsi 50 kredit)")
                lyric_src = dlg.result.get("lyric_source", "deepseek_web")
                cfg = {"description": desc, "quantity": take,
                       "instrumental": instrumental,
                       "lyric_source": lyric_src,
                       "profile_name": p.get("name",""), "bulk_mode": True}
                songs_done = [0]

                def on_done(pp=p, qty=take, box=songs_done):
                    box[0] += 1
                    self.after(0, self.log,
                        f"[BULK] {pp['name']} -> lagu ke-{box[0]}/{qty} berhasil!")

                def on_finish(pp=p):
                    def _inner(created, downloaded, latest_cr):
                        # Selalu ambil object terbaru dari self.profiles (bukan closure stale)
                        _live = self._find_by_dir(self._pdir(pp)) or pp
                        if latest_cr == "CAPTCHA_SKIP":
                            _live["status_info"] = "⚠ CAPTCHA — perlu manual"
                            captcha_profiles.append(_live.get("name", "?"))
                            save_profiles(self.profiles)
                            self.after(0, self.refresh_table)
                            self.after(0, self.log, "=" * 52)
                            self.after(0, self.log, f"  ⚠ CAPTCHA — {_live['name']} di-skip!")
                            self.after(0, self.log, "  Buka Chrome manual → solve CAPTCHA → coba lagi.")
                            self.after(0, self.log, "=" * 52)
                            return
                        # Update kredit pada object LIVE (bukan stale closure)
                        if not _live.get("is_premium", False):
                            if latest_cr is not None:
                                _live["credits_remaining"] = latest_cr
                            elif created > 0:
                                _cur_b = parse_credit_value(_live.get("credits_remaining"))
                                if _cur_b is not None:
                                    _live["credits_remaining"] = max(0, _cur_b - (created * FREE_CREDITS_PER_CREATE))
                        # Update status + simpan + refresh tabel
                        if created > 0:
                            _ls_b = ""
                            try:
                                _dl_b = Path(load_app_config().get("download_dir",
                                             str(Path.home() / "suno_downloads")))
                                _ff_b = sorted(_dl_b.rglob("*.mp3"),
                                               key=lambda x: x.stat().st_mtime, reverse=True)
                                if _ff_b: _ls_b = f" | 🎵 {_ff_b[0].stem[:22]}"
                            except Exception: pass
                            _live["status_info"] = f"✅ Done {created} lagu{_ls_b}"
                        else:
                            _live["status_info"] = "❌ Kredit habis / gagal"
                        save_profiles(self.profiles)
                        self.after(0, self.refresh_table)
                        self.after(0, self.log,
                            f"[BULK] {_live['name']} → sukses: {created}, "
                            f"kredit: {latest_cr if latest_cr is not None else _live.get('credits_remaining','?')}")
                    return _inner

                run_generate(chrome, self._pdir(p), cfg,
                             self._thread_log, on_done, on_finish())
                remain_local -= take

            self._generate_running = False
            self.after(0, lambda: self.buat_btn.state(["!disabled"]))
            self.after(0, lambda: self.stop_btn.state(["disabled"]))
            self.after(0, lambda: self.pause_btn.state(["disabled"]))
            self.after(0, lambda: self.pause_btn.config(text="⏸ Pause"))
            self.after(0, self.refresh_table)
            self.after(0, self.log,
                f"[BULK] Semua profile selesai. Sisa tidak dibuat: {remain_local}")
            if captcha_profiles:
                _cmsg = (f"[BULK] ⚠ {len(captcha_profiles)} profile kena CAPTCHA:\n"
                         + "\n".join(f"  • {n}" for n in captcha_profiles)
                         + "\n[BULK] Buka Chrome manual → solve CAPTCHA → coba lagi.")
                self.after(0, self.log, _cmsg)
                self.after(0, lambda cp=list(captcha_profiles): messagebox.showwarning(
                    "⚠ CAPTCHA Perlu Manual",
                    f"{len(cp)} profile perlu diselesaikan manual:\n\n" +
                    "\n".join(f"• {n}" for n in cp) +
                    "\n\nBuka Chrome → login Suno → solve CAPTCHA → coba lagi dari app."
                ))

        threading.Thread(target=worker, daemon=True).start()

    def download_lagu_selected(self):
        profiles = self.get_selected_profiles()
        if not profiles:
            return
        count = simpledialog.askinteger("Download Lagu", "Jumlah lagu teratas per profile:", minvalue=1)
        if not count:
            return
        chrome = self.chrome_path_var.get().strip()
        if not chrome or not os.path.exists(chrome):
            if messagebox.askyesno("Chrome Tidak Ditemukan",
                "Chrome path belum diset atau tidak valid.\n\n"
                "Klik YES untuk Browse dan pilih chrome.exe sekarang,\n"
                "atau NO untuk batalkan aksi ini."):
                self.browse_chrome()
                chrome = self.chrome_path_var.get().strip()
                if not chrome or not os.path.exists(chrome):
                    return
            else:
                return
        for p in profiles:
            self.log(f"[DL] {p['name']} -> {count} lagu")
            def _dl_worker(profile=p, _chrome=chrome, _count=count):
                run_download_latest_n(_chrome, self._pdir(profile), _count, self._thread_log)
                self._thread_log(f"[DL] ✓ Download selesai untuk {profile['name']}.")
                self.after(0, self.refresh_table)  # refresh tabel saja, tanpa cek kredit
            threading.Thread(target=_dl_worker, daemon=True).start()


if __name__ == "__main__":
    app = AppV2()
    def _on_close():
        try:
            if getattr(app, "_log_file", None):
                app._log_file.write("=== Session Ended ===\n")
                app._log_file.close()
        except Exception:
            pass
        app.destroy()
    app.protocol("WM_DELETE_WINDOW", _on_close)
    app.mainloop()
