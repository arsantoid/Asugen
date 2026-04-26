# ═══════════════════════════════════════════════════════════════════
#  suno_dialogs.py  —  ASuGen
#  Semua dialog Tkinter: AI Settings, Generate, BulkCreate, dll
#  + Playwright async download functions
# ═══════════════════════════════════════════════════════════════════
from suno_core import *
# FIX: import eksplisit semua fungsi prefix _ yang tidak ikut wildcard import
from suno_core import (
    _deepseek_web_prepare_songs, _minimize_chrome_windows, _prompt_to_folder_name,
    _run_async, _stop_requested, _parse_deepseek_response,
    get_stop_event, request_stop, clear_stop, is_stop_requested, is_paused, wait_if_paused, request_pause, resume_generate,
    save_window_position, load_window_position
)

class AISettingsDialog(tk.Toplevel):
    PRESETS = {
        "OpenAI":     ("https://api.openai.com/v1",        "gpt-4o-mini"),
        "Claude":     ("https://api.anthropic.com/v1",     "claude-haiku-4-5"),
        "Groq":       ("https://api.groq.com/openai/v1",   "llama-3.3-70b-versatile"),
        "OpenRouter": ("https://openrouter.ai/api/v1",     ""),
        "DeepSeek":   ("https://api.deepseek.com/v1",      "deepseek-chat"),
        "Custom":     ("", ""),
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.title("AI Settings")
        self.geometry("580x700")
        self.minsize(560, 500)
        self.resizable(True, True)
        self.grab_set()
        cfg = load_ai_config()

        # ── Tombol di-pack PERTAMA → selalu terlihat di bawah ──
        bf = ttk.Frame(self, padding=(8, 6))
        bf.pack(side="bottom", fill="x")
        ttk.Button(bf, text="Test Connection", command=self._test,  width=18).pack(side="left", padx=6)
        ttk.Button(bf, text="Simpan",          command=self._save,  width=12).pack(side="left", padx=6)
        ttk.Button(bf, text="Batal",           command=self.destroy, width=10).pack(side="left", padx=6)
        ttk.Separator(self).pack(side="bottom", fill="x")

        # ── Canvas scrollable ──
        _canvas = tk.Canvas(self, highlightthickness=0)
        _vsb    = ttk.Scrollbar(self, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        frm = ttk.Frame(_canvas, padding=16)
        frm.columnconfigure(1, weight=1)
        _cwin = _canvas.create_window((0, 0), window=frm, anchor="nw")

        def _on_resize(e):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_resize(e):
            _canvas.itemconfig(_cwin, width=e.width)
        frm.bind("<Configure>", _on_resize)
        _canvas.bind("<Configure>", _on_canvas_resize)
        def _on_wheel(e):
            _canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        _canvas.bind_all("<MouseWheel>", _on_wheel)

        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Provider:").grid(row=0, column=0, sticky="w", pady=6)
        pf = ttk.Frame(frm)
        pf.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=6)
        for name in self.PRESETS:
            ttk.Button(pf, text=name, width=10,
                       command=lambda n=name: self._apply_preset(n)).pack(side="left", padx=2)

        ttk.Label(frm, text="API Key:").grid(row=1, column=0, sticky="w", pady=6)
        self.key_var = tk.StringVar(value=cfg.get("api_key", ""))
        self.key_entry = ttk.Entry(frm, textvariable=self.key_var, width=55, show="*")
        self.key_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=6)
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="Show", variable=self.show_key_var,
                        command=self._toggle_show_key).grid(row=1, column=2, padx=4)

        # FIX: Multi API Keys — isi satu key per baris, auto-rotate jika error/rate-limit
        ttk.Label(frm, text="API Keys\n(multi, 1/baris):").grid(row=2, column=0, sticky="nw", pady=6)
        self.keys_text = tk.Text(frm, height=4, width=50, font=("Consolas", 8))
        self.keys_text.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=6)
        _existing_keys = cfg.get("api_keys", [])
        if _existing_keys:
            self.keys_text.insert("1.0", "\n".join(_existing_keys))
        elif cfg.get("api_key"):
            self.keys_text.insert("1.0", cfg["api_key"])
        ttk.Label(
            frm,
            text="↑ Isi 1 key per baris. Jika rate-limit/error → ganti key berikutnya → balik ke atas.",
            foreground="gray", font=("", 8),
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(0, 4))

        ttk.Label(frm, text="Base URL:").grid(row=4, column=0, sticky="w", pady=6)
        self.url_var = tk.StringVar(value=cfg.get("base_url", DEFAULT_AI_CONFIG["base_url"]))
        ttk.Entry(frm, textvariable=self.url_var, width=55).grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        self.model_label = ttk.Label(frm, text="Model:")
        self.model_label.grid(row=5, column=0, sticky="w", pady=6)
        self.model_var = tk.StringVar(value=cfg.get("model", DEFAULT_AI_CONFIG["model"]))
        self.model_entry = ttk.Entry(frm, textvariable=self.model_var, width=55)
        self.model_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=6)

        # Label pengganti untuk OpenRouter — tampil otomatis
        self.model_auto_label = ttk.Label(
            frm,
            text="⚡ Auto chain (lihat daftar di bawah) — tidak perlu diisi",
            foreground="#0080a0", font=("", 9, "italic"),
        )
        self.model_auto_label.grid(row=5, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=6)

        # Bind URL change → update tampilan model
        self.url_var.trace_add("write", lambda *_: self._update_model_visibility())
        self._update_model_visibility()

        ttk.Label(frm,
            text="Provider & auth:\n"
                 "• OpenAI / Groq / OpenRouter / DeepSeek → Bearer token\n"
                 "• Claude (Anthropic) → x-api-key header (deteksi otomatis dari URL)\n"
                 "• Tanpa API key → pakai built-in generator\n"
                 "• Model urutan prioritas (1=utama, auto-fallback ke berikutnya):\n"
                "  1. openai/gpt-4o-mini  ← UTAMA (murah, trial OK)\n"
                "  2. google/gemini-2.0-flash-lite-001\n"
                "  3. openai/gpt-4.1-nano\n"
                "  4. anthropic/claude-haiku-4-5\n"
                "  5. mistralai/mistral-small-3.2-24b-instruct\n"
                "  6+. Model gratis :free (fallback, tidak perlu saldo)",
            foreground="gray", font=("", 8), justify="left",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 12))

        self.test_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.test_var, foreground="blue",
                  font=("", 9)).grid(row=7, column=0, columnspan=3, sticky="w")

        self.wait_window()

    def _update_model_visibility(self):
        """Sembunyikan field Model jika OpenRouter — auto-chain dipakai."""
        is_or = "openrouter.ai" in self.url_var.get().strip().lower()
        if is_or:
            self.model_entry.grid_remove()
            self.model_auto_label.grid(row=5, column=1, columnspan=2,
                                       sticky="w", padx=(8, 0), pady=6)
            self.model_var.set(OPENROUTER_FREE_MODELS[0])
        else:
            self.model_auto_label.grid_remove()
            self.model_entry.grid(row=5, column=1, columnspan=2,
                                  sticky="ew", padx=(8, 0), pady=6)

    def _toggle_show_key(self):
        self.key_entry.config(show="" if self.show_key_var.get() else "*")

    def _apply_preset(self, name):
        url, model = self.PRESETS[name]
        if url: self.url_var.set(url)
        if model: self.model_var.set(model)

    def _test(self):
        cfg = {"api_key": self.key_var.get().strip(),
               "base_url": self.url_var.get().strip(),
               "model": self.model_var.get().strip()}
        if not cfg["api_key"]:
            self.test_var.set("❌ API Key kosong!")
            return
        self.test_var.set("⏳ Testing...")
        self.update()
        def do_test():
            try:
                result = call_ai([{"role": "user", "content": "Say OK only."}],
                                 cfg, max_tokens=10, temperature=0)
                self.test_var.set(f"✅ Berhasil! Response: {result[:60]}")
            except Exception as e:
                self.test_var.set(f"❌ Error: {str(e)[:80]}")
        threading.Thread(target=do_test, daemon=True).start()

    def _save(self):
        # FIX: simpan semua key dari textarea multi-key
        raw_keys = self.keys_text.get("1.0", "end").strip().splitlines()
        clean_keys = [k.strip() for k in raw_keys if k.strip()]
        cfg = {
            "api_key":    clean_keys[0] if clean_keys else self.key_var.get().strip(),
            "api_keys":   clean_keys,
            "base_url":   self.url_var.get().strip(),
            "model":      self.model_var.get().strip(),
            "_key_index": 0,
        }
        save_ai_config(cfg)
        n = len(clean_keys)
        messagebox.showinfo("Tersimpan",
            f"AI config berhasil disimpan!\n{n} API key tersimpan.")
        self.destroy()


# ------------------------------------------------------------------
# Generate Song Dialog
# ------------------------------------------------------------------


class GenerateDialog(tk.Toplevel):
    _PLACEHOLDER = "Contoh: rnb, female vocal, warm electric piano, 75bpm, soulful healing"
    _LANGS = [
        "Auto (dari deskripsi)",
        "English", "Indonesia", "Jawa",
        "Español (Spanish)", "Italiano (Italian)",
        "Português (Portuguese)", "Français (French)",
        "Deutsch (German)", "日本語 (Japanese)",
        "한국어 (Korean)", "العربية (Arabic)",
        "हिन्दी (Hindi)", "Mandarin Chinese",
        "Русский (Russian)", "Türkçe (Turkish)",
    ]

    def __init__(self, parent, profile_name: str, available_songs: int, max_from_credits: int = None):
        """
        available_songs : quota berdasarkan MAX_CREATES (batas harian script)
        max_from_credits: floor(credits / 10) tanpa batasan MAX_CREATES.
        """
        super().__init__(parent)
        self.title("Buat Lagu")
        self.geometry("530x500")
        self.minsize(530, 420)
        self.resizable(True, True)
        self.grab_set()
        self.result = None
        self._all_tokens_qty = 0

        if max_from_credits is None:
            max_from_credits = available_songs

        color    = "red" if available_songs <= 1 else ("orange" if available_songs <= 2 else "green")
        ai_cfg   = load_ai_config()
        ai_ok    = bool(ai_cfg.get("api_key", "").strip())
        ai_status = f"\u2705 AI ({ai_cfg['model']})" if ai_ok else "\u26a0\ufe0f built-in"

        # ── Header fixed ──
        hdr = ttk.Frame(self, padding=(12, 10, 12, 4))
        hdr.pack(fill="x")
        ttk.Label(hdr, text=f"Profile: {profile_name}", font=("", 10, "bold")).pack(side="left")
        ttk.Label(hdr, text=f"  |  Sisa: {available_songs}", foreground=color).pack(side="left")
        if max_from_credits > available_songs:
            ttk.Label(hdr, text=f"  |  Kredit cukup: {max_from_credits} lagu",
                      foreground="blue", font=("", 8)).pack(side="left")
        ttk.Label(hdr, text=f"  |  {ai_status}",
                  foreground="green" if ai_ok else "orange", font=("", 8)).pack(side="left")
        ttk.Separator(self).pack(fill="x")

        # ── Scrollable body ──
        _body   = ttk.Frame(self)
        _body.pack(fill="both", expand=True)
        _canvas = tk.Canvas(_body, highlightthickness=0)
        _vsb    = ttk.Scrollbar(_body, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)
        form    = ttk.Frame(_canvas, padding=(12, 8, 12, 8))
        _win_id = _canvas.create_window((0, 0), window=form, anchor="nw")

        def _on_frame_cfg(_e=None):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_cfg(e):
            _canvas.itemconfig(_win_id, width=e.width)
        form.bind("<Configure>", _on_frame_cfg)
        _canvas.bind("<Configure>", _on_canvas_cfg)

        def _mwheel(e):
            _canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        _canvas.bind_all("<MouseWheel>", _mwheel)
        self.bind("<Destroy>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        form.columnconfigure(1, weight=1)

        # Row 0: Music Style
        ttk.Label(form, text="Music Style:").grid(row=0, column=0, sticky="nw", pady=6)
        self.desc_text = tk.Text(form, width=42, height=4, wrap="word")
        self.desc_text.grid(row=0, column=1, sticky="ew", padx=(8,0), pady=6)
        self.desc_text.insert("1.0", self._PLACEHOLDER)
        self.desc_text.bind("<FocusIn>", self._clear_placeholder)
        self.desc_text.config(foreground="gray")

        # Row 1: hint
        ttk.Label(form,
                  text="Style ini BAKU \u2014 sama untuk SEMUA lagu. Lirik berbeda per lagu (AI).",
                  foreground="gray", font=("", 8),
                  ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0,4))

        # Row 2: Jumlah Lagu
        ttk.Label(form, text="Jumlah Lagu:").grid(row=2, column=0, sticky="w", pady=6)
        qf = ttk.Frame(form)
        qf.grid(row=2, column=1, sticky="w", padx=(8,0), pady=6)
        self.qty_var  = tk.IntVar(value=1)
        radio_max     = min(5, max(1, available_songs))
        for val in range(1, radio_max + 1):
            ttk.Radiobutton(qf, text=str(val), variable=self.qty_var, value=val).pack(side="left", padx=4)

        # Row 3: Habiskan Semua Token
        self.qty_info_var = tk.StringVar(value="")
        if max_from_credits > available_songs and max_from_credits > 0:
            ttk.Button(form,
                       text=f"\U0001f50b Habiskan Semua Token ({max_from_credits} lagu)",
                       command=lambda: self._set_all_tokens(max_from_credits), width=36,
                       ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4,0))
        ttk.Label(form, textvariable=self.qty_info_var, foreground="blue",
                  font=("", 9)).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2,0))

        # Row 5: Bahasa Lirik
        ttk.Label(form, text="Bahasa Lirik:").grid(row=5, column=0, sticky="w", pady=6)
        self.lang_var = tk.StringVar(value="Auto (dari deskripsi)")
        ttk.Combobox(form, textvariable=self.lang_var, values=self._LANGS,
                     state="readonly", width=30).grid(row=5, column=1, sticky="w", padx=(8,0), pady=6)

        # Row 6: Instrumental
        self.instrumental_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Instrumental (no vocals)",
                        variable=self.instrumental_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)

        # Row 7: Sumber Lirik
        ttk.Label(form, text="Sumber Lirik:").grid(row=7, column=0, sticky="w", pady=4)
        self.lyric_source_var = tk.StringVar(value="deepseek_web")
        _lsf = ttk.Frame(form)
        _lsf.grid(row=7, column=1, sticky="w")
        ttk.Radiobutton(_lsf, text="OpenRouter / API",
                        variable=self.lyric_source_var, value="api").pack(side="left", padx=(0,10))
        ttk.Radiobutton(_lsf, text="DeepSeek Web (browser, gratis - login dulu)",
                        variable=self.lyric_source_var, value="deepseek_web").pack(side="left")

        # ── Footer fixed ──
        ttk.Separator(self).pack(fill="x")
        bf = ttk.Frame(self, padding=(0,8))
        bf.pack()
        ttk.Button(bf, text="Buat Lagu", command=self._confirm, width=16).pack(side="left", padx=8)
        ttk.Button(bf, text="Batal",     command=self.destroy,  width=10).pack(side="left", padx=8)
        self.wait_window()

    def _set_all_tokens(self, max_lagu: int):
        self._all_tokens_qty = max_lagu
        self.qty_var.set(max_lagu)
        self.qty_info_var.set(
            f"\u2705 Mode Habiskan Semua: {max_lagu} lagu akan digenerate (melewati batas harian {MAX_CREATES})"
        )

    def _clear_placeholder(self, _):
        if self.desc_text.get("1.0", "end").strip() == self._PLACEHOLDER:
            self.desc_text.delete("1.0", "end")
            self.desc_text.config(foreground="black")

    def _confirm(self):
        desc = self.desc_text.get("1.0", "end").strip()
        if not desc or desc == self._PLACEHOLDER:
            messagebox.showwarning("Input kosong", "Isi Music Style dulu.")
            return
        qty  = self._all_tokens_qty if self._all_tokens_qty > 0 else self.qty_var.get()
        lang = self.lang_var.get()
        lang_clean = "" if lang.startswith("Auto") else lang.split(" (")[0]
        self.result = {
            "description":  desc,
            "quantity":     qty,
            "instrumental": self.instrumental_var.get(),
            "lyric_source": self.lyric_source_var.get(),
            "language":     lang_clean,
        }
        self.destroy()

class BulkCreateDialog(tk.Toplevel):
    _PLACEHOLDER = "Contoh: rnb, female vocal, warm electric piano, 75bpm, soulful healing"
    _LANGS = [
        "Auto (dari deskripsi)",
        "English", "Indonesia", "Jawa",
        "Español (Spanish)", "Italiano (Italian)",
        "Português (Portuguese)", "Français (French)",
        "Deutsch (German)", "日本語 (Japanese)",
        "한국어 (Korean)", "العربية (Arabic)",
        "हिन्दी (Hindi)", "Mandarin Chinese",
        "Русский (Russian)", "Türkçe (Turkish)",
    ]

    def __init__(self, parent, profiles: list, total_available: int):
        super().__init__(parent)
        self.title("Bulk Create")
        self.geometry("700x680")
        self.minsize(700, 540)
        self.resizable(True, True)
        self.grab_set()
        self.result = None
        self._profiles = profiles
        self._cap = self._calc_capacity(profiles)
        total_real_max = self._cap["total_can_create"]

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        # ── Header ringkasan ──
        hdr = ttk.LabelFrame(outer, text="Ringkasan Kapasitas", padding=8)
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(8,4))
        hdr.columnconfigure(1, weight=1)
        def _lbl(row, label, value, color=None):
            ttk.Label(hdr, text=label, width=26, anchor="w").grid(row=row, column=0, sticky="w")
            lw = ttk.Label(hdr, text=value, anchor="w", foreground=color or "")
            lw.grid(row=row, column=1, sticky="w")
            return lw
        _lbl(0, "Profile dipilih:", f"{len(profiles)} profile")
        _lbl(1, "Total kredit tersimpan:",
             f"{self._cap['total_credits']:,} kredit" +
             (" (\u26a0 ada profil belum dicek)" if self._cap["has_unknown"] else ""),
             "orange" if self._cap["has_unknown"] else "green")
        _lbl(2, "Maks bisa generate:",
             f"{total_real_max} lagu  (@{FREE_CREDITS_PER_CREATE}kr/lagu, maks {MAX_SONGS_PER_PROFILE}/profil)",
             "blue")
        _lbl(3, "Profil aktif (\u226510 kredit):",
             f"{self._cap['active_profiles']} dari {len(profiles)} profil",
             "green" if self._cap["active_profiles"] > 0 else "red")

        # ── Scrollable form ──
        _fo = ttk.Frame(outer)
        _fo.grid(row=1, column=0, sticky="ew", padx=10, pady=(4,0))
        _fo.columnconfigure(0, weight=1)
        _canvas = tk.Canvas(_fo, highlightthickness=0, height=230)
        _vsb    = ttk.Scrollbar(_fo, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)
        form    = ttk.Frame(_canvas, padding=(4,4,4,4))
        _win_id = _canvas.create_window((0,0), window=form, anchor="nw")

        def _on_frame_cfg(_e=None):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_cfg(e):
            _canvas.itemconfig(_win_id, width=e.width)
        form.bind("<Configure>", _on_frame_cfg)
        _canvas.bind("<Configure>", _on_canvas_cfg)

        def _mwheel(e):
            _canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        _canvas.bind_all("<MouseWheel>", _mwheel)
        self.bind("<Destroy>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        form.columnconfigure(1, weight=1)

        # Row 0: Music Style
        ttk.Label(form, text="Music Style:").grid(row=0, column=0, sticky="nw", pady=6)
        self.desc_text = tk.Text(form, width=56, height=4, wrap="word")
        self.desc_text.grid(row=0, column=1, sticky="ew", pady=6)
        self.desc_text.insert("1.0", self._PLACEHOLDER)
        self.desc_text.bind("<FocusIn>", self._clear_placeholder)
        self.desc_text.config(foreground="gray")

        # Row 1: Total lagu
        ttk.Label(form, text="Total lagu:").grid(row=1, column=0, sticky="w", pady=6)
        qf = ttk.Frame(form)
        qf.grid(row=1, column=1, sticky="w", pady=6)
        self.qty_var   = tk.IntVar(value=max(1, total_real_max))
        self._qty_spin = ttk.Spinbox(qf, from_=1, to=max(1, total_real_max),
                                     textvariable=self.qty_var, width=8,
                                     command=self._on_qty_change)
        self._qty_spin.pack(side="left")
        ttk.Label(qf, text=f"  (maks {total_real_max})", foreground="gray").pack(side="left")
        ttk.Button(qf, text="Max", width=5,
                   command=lambda: [self.qty_var.set(total_real_max), self._on_qty_change()]
                   ).pack(side="left", padx=(8,0))
        self.qty_var.trace_add("write", lambda *_: self.after(50, self._on_qty_change))

        # Row 2: Bahasa Lirik
        ttk.Label(form, text="Bahasa Lirik:").grid(row=2, column=0, sticky="w", pady=6)
        self.lang_var = tk.StringVar(value="Auto (dari deskripsi)")
        ttk.Combobox(form, textvariable=self.lang_var, values=self._LANGS,
                     state="readonly", width=30).grid(row=2, column=1, sticky="w", pady=6)

        # Row 3: Instrumental
        self.instrumental_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Instrumental (no vocals)",
                        variable=self.instrumental_var).grid(row=3, column=1, sticky="w", pady=(0,4))

        # Row 4: Sumber Lirik
        ttk.Label(form, text="Sumber Lirik:").grid(row=4, column=0, sticky="w", pady=4)
        self.lyric_source_var = tk.StringVar(value="deepseek_web")
        _blsf = ttk.Frame(form)
        _blsf.grid(row=4, column=1, sticky="w")
        ttk.Radiobutton(_blsf, text="OpenRouter / API",
                        variable=self.lyric_source_var, value="api").pack(side="left", padx=(0,10))
        ttk.Radiobutton(_blsf, text="DeepSeek Web (browser, gratis - login dulu)",
                        variable=self.lyric_source_var, value="deepseek_web").pack(side="left")

        # ── Preview treeview ──
        cols = ("name","credit","can_create","dapat","status")
        box = ttk.LabelFrame(outer, text="Preview Distribusi (update otomatis)")
        box.grid(row=2, column=0, sticky="nsew", padx=10, pady=(6,4))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        self.preview = ttk.Treeview(box, columns=cols, show="headings", height=8)
        self.preview.heading("name",       text="Profil")
        self.preview.heading("credit",     text="Kredit")
        self.preview.heading("can_create", text="Bisa Create")
        self.preview.heading("dapat",      text="Dapat \u2728")
        self.preview.heading("status",     text="Status")
        self.preview.column("name",       width=195)
        self.preview.column("credit",     width=80,  anchor="center")
        self.preview.column("can_create", width=85,  anchor="center")
        self.preview.column("dapat",      width=80,  anchor="center")
        self.preview.column("status",     width=115, anchor="center")
        self.preview.grid(row=0, column=0, sticky="nsew")
        _tsb = ttk.Scrollbar(box, command=self.preview.yview)
        self.preview.configure(yscrollcommand=_tsb.set)
        _tsb.grid(row=0, column=1, sticky="ns")
        self.preview.tag_configure("skip", foreground="gray")
        self.preview.tag_configure("ok",   foreground="green")

        # ── Footer fixed ──
        ttk.Separator(outer).grid(row=3, column=0, sticky="ew", pady=(4,0))
        bf = ttk.Frame(outer, padding=(0,6))
        bf.grid(row=4, column=0, sticky="e", padx=10, pady=(0,8))
        ttk.Button(bf, text="Start Bulk Create", command=self._confirm, width=18).pack(side="left", padx=6)
        ttk.Button(bf, text="Batal",             command=self.destroy,  width=10).pack(side="left", padx=6)

        self._on_qty_change()
        self.wait_window()

    @staticmethod
    def _calc_capacity(profiles):
        total_cr, total_can, active, has_unk = 0, 0, 0, False
        for p in profiles:
            if p.get("is_premium"):
                total_can += MAX_SONGS_PER_PROFILE; active += 1; continue
            cr = parse_credit_value(p.get("credits_remaining"))
            if cr is None: cr = ASSUMED_CREDITS_PER_PROFILE; has_unk = True
            total_cr += cr
            can = min(MAX_SONGS_PER_PROFILE, cr // FREE_CREDITS_PER_CREATE)
            total_can += can
            if can > 0: active += 1
        return {"total_credits": total_cr, "total_can_create": total_can,
                "active_profiles": active, "has_unknown": has_unk}

    def _distribute(self, qty):
        rows = []
        for p in self._profiles:
            if p.get("is_premium"):
                rows.append({"p":p,"can":MAX_SONGS_PER_PROFILE,"cr_label":"Pro \u221e"})
            else:
                cr  = parse_credit_value(p.get("credits_remaining"))
                unk = cr is None
                if cr is None: cr = ASSUMED_CREDITS_PER_PROFILE
                can = min(MAX_SONGS_PER_PROFILE, cr // FREE_CREDITS_PER_CREATE)
                rows.append({"p":p,"can":can,"cr_label":(f"{cr}\u26a0" if unk else str(cr))})
        rows.sort(key=lambda x: x["can"], reverse=True)
        remain = qty
        for r in rows:
            give = min(r["can"], remain); r["dapat"] = give; remain -= give
        return rows

    def _on_qty_change(self):
        try: qty = max(1, int(self.qty_var.get()))
        except Exception: qty = 1
        qty  = min(qty, self._cap["total_can_create"])
        rows = self._distribute(qty)
        for item in self.preview.get_children(): self.preview.delete(item)
        for r in rows:
            p, can, got = r["p"], r["can"], r["dapat"]
            if p.get("is_premium"):   status = "Pro \u2713"
            elif can == 0:            status = "\u26d4 skip (0kr)"
            elif got == 0:            status = "\u23ed tidak perlu"
            else:                     status = f"\u2705 {got} lagu"
            tag = "skip" if got == 0 else "ok"
            self.preview.insert("","end",
                values=(p.get("name",""), r["cr_label"], can, got if got>0 else "-", status),
                tags=(tag,))

    def _clear_placeholder(self, _):
        if self.desc_text.get("1.0","end").strip() == self._PLACEHOLDER:
            self.desc_text.delete("1.0","end")
            self.desc_text.config(foreground="black")

    def _confirm(self):
        desc = self.desc_text.get("1.0","end").strip()
        if not desc or desc == self._PLACEHOLDER:
            messagebox.showwarning("Input kosong","Isi Music Style dulu."); return
        qty  = max(1, int(self.qty_var.get() or 1))
        lang = self.lang_var.get()
        lang_clean = "" if lang.startswith("Auto") else lang.split(" (")[0]
        self.result = {
            "description":  desc,
            "quantity":     qty,
            "instrumental": self.instrumental_var.get(),
            "lyric_source": self.lyric_source_var.get(),
            "language":     lang_clean,
            "distribution": self._distribute(qty),
        }
        self.destroy()

class AddProfileDialog(tk.Toplevel):
    def __init__(self, parent, title="Add Profile", initial_name="", initial_email=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x170")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Name:").grid(row=0, column=0, sticky="w", pady=6)
        self.name_var = tk.StringVar(value=initial_name)
        name_entry = ttk.Entry(frm, textvariable=self.name_var, width=36)
        name_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(frm, text="Email:").grid(row=1, column=0, sticky="w", pady=6)
        self.email_var = tk.StringVar(value=initial_email)
        ttk.Entry(frm, textvariable=self.email_var, width=36).grid(row=1, column=1, sticky="ew", pady=6)

        ttk.Label(frm, text="Email boleh kosong.", foreground="gray").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        bf = ttk.Frame(frm)
        bf.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(bf, text="Simpan", command=self._confirm, width=12).pack(side="left", padx=6)
        ttk.Button(bf, text="Batal", command=self.destroy, width=10).pack(side="left", padx=6)

        name_entry.focus_set()
        self.bind("<Return>", lambda _e: self._confirm())
        self.wait_window()

    def _confirm(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Input kosong", "Name wajib diisi.")
            return
        self.result = {
            "name": name,
            "email": self.email_var.get().strip(),
        }
        self.destroy()


# ------------------------------------------------------------------
# JS inject helper
# ------------------------------------------------------------------

async def js_set_value(el, text: str):
    await el.evaluate("""
        (el, text) => {
            const tag = el.tagName;
            if (tag === 'TEXTAREA' || tag === 'INPUT') {
                const proto = tag === 'TEXTAREA'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(el, text);
            } else if (el.isContentEditable) {
                el.innerText = text;
            }
            el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
    """, text)


# ------------------------------------------------------------------
# Playwright: generate one song
# ------------------------------------------------------------------

async def _generate_one_song(context, song_config: dict, song_index: int, total: int, log_cb):
    import asyncio
    if is_stop_requested():
        log_cb(f"[STOP] Lagu {song_index}/{total} dibatalkan.")
        return None

    title  = song_config["title"]
    style  = song_config["style"]
    lyrics = song_config["lyrics"] if not song_config.get("instrumental") else ""

    log_cb(f"\n{'='*50}")
    log_cb(f"[{song_index}/{total}] Generating: {title}")
    log_cb(f"  Style : {style[:70]}...")
    log_cb(f"  Lyrics: {len(lyrics.splitlines())} baris | {len(lyrics)} karakter")

    # PATCH: cek panjang lirik sebelum mulai buka browser
    # FIX: lofi/semi-instrumental boleh lirik pendek (min 400 char)
    _style_lower = style.lower() if style else ""
    _is_lofi_skip = any(kw in _style_lower for kw in [
        "lofi", "lo-fi", "lo fi", "chillhop", "chill hop", "study beats", "chill beats",
        "relaxing study", "rain ambiance", "vinyl crackle", "tape saturation"
    ])
    _min_skip = 200 if _is_lofi_skip else MIN_LYRICS_CHARS
    if not song_config.get("instrumental") and len(lyrics) < _min_skip:
        log_cb(
            f"  [SKIP] Lirik hanya {len(lyrics)} karakter < {_min_skip} minimum.\n"
            f"  [SKIP] Lagu ini di-skip untuk hemat kredit Suno.\n"
            f"  [SKIP] Harap periksa AI config atau coba lagi."
        )
        return None

    pages = context.pages
    page = pages[0] if pages else await context.new_page()

    log_cb(f"[{song_index}/{total}][1/5] Opening suno.com/create...")
    _goto_song_ok = False
    for _gurl in ["https://suno.com/create", "https://suno.com"]:
        try:
            await page.goto(_gurl, wait_until="commit", timeout=35000)
            await asyncio.sleep(2)
            if "about:blank" not in page.url and "chrome-error" not in page.url:
                _goto_song_ok = True
                log_cb(f"  OK: {page.url[:60]}")
                break
        except Exception as e:
            log_cb(f"  warning goto {_gurl}: {str(e)[:60]}")
    if not _goto_song_ok:
        log_cb("  ❌ Gagal buka suno.com. Cek koneksi internet.")
        return
    await asyncio.sleep(5)
    if "/sign-in" in page.url or "/login" in page.url:
        log_cb("  GAGAL: Belum login!")
        return None

    log_cb(f"[{song_index}/{total}][2/5] Custom / Advanced mode...")
    # Klik semua kemungkinan tombol Custom/Advanced mode dan verifikasi
    custom_selectors = [
        "button:has-text('Custom')",
        "[role='tab']:has-text('Custom')",
        "label:has-text('Custom')",
        "[data-testid='custom-tab']",
        "button:has-text('Advanced')",
        "[role='tab']:has-text('Advanced')",
        "label:has-text('Advanced')",
        "[aria-label*='custom' i]",
        "[aria-label*='advanced' i]",
    ]
    custom_clicked = False
    for sel in custom_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=2000, state="visible")
            if el:
                await el.click()
                await asyncio.sleep(1.5)
                log_cb(f"  Klik: {sel}")
                custom_clicked = True
                break
        except Exception:
            continue

    if not custom_clicked:
        log_cb("  INFO: Tombol Custom/Advanced tidak ditemukan — lanjut (mungkin sudah aktif)")

    if is_stop_requested():
        return None

    log_cb(f"[{song_index}/{total}][3/5] Form fields...")
    # Tunggu minimal 2 textarea muncul (lyrics + style)
    try:
        await page.wait_for_selector("textarea", timeout=12000, state="visible")
        await asyncio.sleep(2)
    except Exception:
        log_cb("  WARNING: textarea tidak ditemukan")

    # Verifikasi ada 2 textarea (custom mode aktif)
    ta_total = await page.locator("textarea").count()
    log_cb(f"  Textarea count: {ta_total}")
    if ta_total < 2:
        # Coba klik lagi semua selector custom/advanced
        log_cb("  Hanya 1 textarea — coba klik Custom/Advanced lagi...")
        for sel in custom_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(2)
                    ta_total = await page.locator("textarea").count()
                    log_cb(f"  Setelah klik {sel}: {ta_total} textarea")
                    if ta_total >= 2:
                        break
            except Exception:
                continue

    if lyrics:
        try:
            ta0 = page.locator("textarea").nth(0)
            await ta0.scroll_into_view_if_needed()
            await ta0.click()
            await asyncio.sleep(0.3)
            await js_set_value(await ta0.element_handle(), lyrics)
            await asyncio.sleep(0.5)
            val = await ta0.input_value()
            log_cb(f"  OK: Lyrics {len(val)} chars")
            # PATCH: warning jika lyrics yang masuk form terlalu pendek
            if len(val) < MIN_LYRICS_CHARS:
                log_cb(
                    f"  [WARN] Lyrics di form hanya {len(val)} char "
                    f"(minimum {MIN_LYRICS_CHARS}). Akan tetap dicreate."
                )
        except Exception as e:
            log_cb(f"  ERROR lyrics: {e}")

    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)  # FIX: lebih cepat
        await page.evaluate("window.scrollBy(0, 350)")  # scroll lebih jauh agar title field langsung visible
        await asyncio.sleep(0.2)
    except Exception:
        pass

    log_cb(f"[{song_index}/{total}][4/5] Filling Style...")
    filled_style = False
    try:
        ta_count = await page.locator("textarea").count()
        style_loc = page.locator("textarea").nth(1 if ta_count >= 2 else 0)
        await style_loc.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)
        style_el = await style_loc.element_handle()
        await style_el.evaluate("el => { el.focus(); el.click(); }")
        await asyncio.sleep(0.4)
        await style_loc.press("Control+a")
        await style_loc.press("Delete")
        await js_set_value(style_el, style)
        await asyncio.sleep(0.5)
        val = await style_loc.input_value()
        if val.strip():
            log_cb(f"  OK: Style ({len(val)} chars): {val[:60]}")
            filled_style = True
    except Exception as e:
        log_cb(f"  ERROR style: {e}")

    if not filled_style:
        log_cb("  SKIP: Style tidak terisi")
        return None

    # ── Isi Song Title — v5.45: scroll bawah + JS langsung ────────────
    # Tidak ada selector hunting, tidak ada More Options, tidak ada wait.
    # Scroll mentok bawah → JS cari & isi input title seketika.
    _title_filled = False
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.3)

        _js_title = await page.evaluate(r"""(titleVal) => {
            const kws = ['title', 'song title', 'optional', 'song name'];
            const inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
            for (const inp of inputs) {
                const ph  = (inp.placeholder || '').toLowerCase();
                const lbl = (inp.getAttribute('aria-label') || '').toLowerCase();
                const nm  = (inp.name || '').toLowerCase();
                const hit = kws.some(k => ph.includes(k) || lbl.includes(k) || nm.includes(k));
                if (hit) {
                    inp.scrollIntoView({behavior:'instant', block:'center'});
                    inp.focus();
                    inp.click();
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(inp, titleVal);
                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                    return inp.value;
                }
            }
            return null;
        }""", title)

        if _js_title:
            _title_filled = True
            log_cb(f"  OK: Title = {_js_title}")
        else:
            log_cb(f"  INFO: Title input tidak ditemukan — Suno auto-generate judul")
            log_cb(f"  INFO: Nama FILE tetap pakai judul DeepSeek: {title}")
    except Exception as _te:
        log_cb(f"  INFO: Title skip: {_te.__class__.__name__}")

    await asyncio.sleep(0.3)
    if is_stop_requested():
        return None

    log_cb(f"[{song_index}/{total}][5/5] Clicking Create...")
    clicked = False
    for sel in ["button:has-text('Create')", "button:has-text('Generate')",
                "[data-testid='create-button']", "button[type='submit']"]:
        try:
            el = await page.wait_for_selector(sel, timeout=5000, state="visible")
            if el and await el.get_attribute("disabled") is None:
                await el.scroll_into_view_if_needed()
                import random as _rmv
                _box = await el.bounding_box()
                if _box:
                    _cx = _box["x"] + _box["width"] / 2
                    _cy = _box["y"] + _box["height"] / 2
                    await page.mouse.move(_cx + _rmv.randint(-80,80), _cy + _rmv.randint(-60,60))
                    await asyncio.sleep(_rmv.uniform(0.15, 0.35))
                    await page.mouse.move(_cx, _cy, steps=_rmv.randint(5, 12))
                    await asyncio.sleep(_rmv.uniform(0.05, 0.15))
                await el.click()
                log_cb(f"  OK: Create clicked! Lagu {song_index}/{total} sedang generate...")
                clicked = True
                break
        except Exception:
            continue

    if clicked:
        # PATCH: re-check captcha setelah klik Create
        # CF Turnstile/hCaptcha kadang muncul SETELAH form submit
        import asyncio as _ac
        await _ac.sleep(2)
        _profile_name_local = song_config.get("profile_name", "")
        captcha_after = await _check_and_handle_captcha(page, log_cb, _profile_name_local)
        if not captcha_after:
            log_cb(
                f"  [CAPTCHA] Captcha muncul setelah Create di lagu {song_index}. "
                f"Lagu mungkin tidak tergenerate — lanjut ke berikutnya."
            )
    if not clicked:
        log_cb("  WARNING: Create button tidak ditemukan")
        try:
            body_text = (await page.inner_text("body")).lower()
            if ("0 credits" in body_text or "not enough credits" in body_text
                    or "insufficient" in body_text):
                log_cb("  [KREDIT] Kredit habis terdeteksi -> sinyal NO_CREDIT.")
                return "NO_CREDIT"
        except Exception:
            pass
    return title if clicked else None


# ------------------------------------------------------------------
# Main generate runner
# ------------------------------------------------------------------

# ---------------------------------------------------------------
# Helper: threshold KB berdasarkan style (lofi vs normal)
# ---------------------------------------------------------------
def run_generate(chrome_path: str, profile_dir: str, config: dict, log_cb, done_cb=None, finish_cb=None):
    profile_dir = resolve_profile_dir(profile_dir)  # FIX portable path
    import asyncio
    lyric_source = config.get("lyric_source", "api")  # "api" | "deepseek_web"
    if lyric_source == "deepseek_web":
        log_cb("\n[DS-WEB] Mode DeepSeek Web aktif - lirik digenerate via browser.")
        log_cb("[DS-WEB] Pastikan sudah login chat.deepseek.com di profil Chrome ini!")
        songs = []
    else:
        log_cb("\n[AI/GEN] Menyiapkan konten lagu...")
        songs = prepare_songs_with_ai(config, log_cb)
        if not songs:
            log_cb("[ERROR] Gagal menyiapkan konten lagu.")
            return
    _pname = config.get("profile_name", "")
    for _s in songs:
        if "profile_name" not in _s:
            _s["profile_name"] = _pname
    try:
        _run_async(_async_generate(chrome_path, profile_dir, config, songs, log_cb, done_cb, finish_cb))
    except Exception as e:
        log_cb(f"ERROR: {e}")


async def _async_generate(chrome_path, profile_dir, config, songs, log_cb, done_cb, finish_cb=None):
    import asyncio
    _stop_ev = get_stop_event()   # FIX: stop singleton dari suno_core
    quantity = len(songs)
    log_cb(f"\n[START] Launching Chrome: {Path(profile_dir).name}")

    latest_credits = None

    async with (await _launch_context(chrome_path, profile_dir, log_cb)) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        log_cb("[CHECK] Verifikasi login Suno...")
        _chk_ok = False
        for _curl in ["https://suno.com/create", "https://suno.com"]:
            try:
                await page.goto(_curl, wait_until="commit", timeout=35000)
                await asyncio.sleep(2)
                if "about:blank" not in page.url and "chrome-error" not in page.url:
                    _chk_ok = True
                    log_cb(f"  OK: {page.url[:60]}")
                    break
            except Exception as e:
                log_cb(f"  warning goto {_curl}: {str(e)[:60]}")
        if not _chk_ok:
            log_cb("  ❌ Gagal buka suno.com. Cek koneksi internet.")
            if finish_cb:
                try: finish_cb(0, 0, None)
                except Exception: pass
            return
        await asyncio.sleep(5)
        if "/sign-in" in page.url or "/login" in page.url:
            log_cb("GAGAL: Belum login!")
            return
        log_cb("  OK: Logged in")

        # PATCH: cek captcha di awal (expanded detection)
        _profile_name = config.get("profile_name", "")
        import asyncio as _aci
        await _aci.sleep(3)  # beri waktu CF challenge load
        captcha_ok = await _check_and_handle_captcha(page, log_cb, _profile_name)
        if not captcha_ok:
            log_cb(
                "  [CAPTCHA] ⏭ Profile di-skip karena captcha tidak selesai.\n"
                "  Status profile diupdate ke '⚠ CAPTCHA' di tabel.\n"
                "  Saran: buka Chrome manual → selesaikan CF challenge → coba lagi."
            )
            if finish_cb:
                try: finish_cb(0, 0, "CAPTCHA_SKIP")
                except Exception: pass
            return

        # DeepSeek Web: generate lirik setelah browser terbuka
        if config.get("lyric_source") == "deepseek_web":
            log_cb("[DS-WEB] Browser siap. Membuka DeepSeek untuk generate lirik...")
            _ds_timeout = config.get("deepseek_web_timeout", 120)
            songs = await _deepseek_web_prepare_songs(context, config, log_cb, _ds_timeout)
            if not songs:
                log_cb("[DS-WEB] GAGAL: Tidak ada lagu disiapkan. Batal.")
                if finish_cb:
                    try: finish_cb(0, 0, None)
                    except Exception: pass
                return
            quantity = len(songs)
            log_cb(f"[DS-WEB] {quantity} lagu siap - lanjut ke Suno Create.")

        generated_titles = []
        songs_generated = 0
        # FIX: simpan untuk auto-reopen
        _ar_chrome_path   = chrome_path
        _ar_profile_dir   = profile_dir
        _ar_managed_ctx   = None   # akan di-set setelah async with

        # Cek kredit SEBELUM generate — pakai new page agar tidak ganggu halaman create
        credits_before = None
        log_cb("[KREDIT] Cek kredit awal sebelum generate...")
        credits_before = await _check_credits_in_context(context, log_cb)
        if credits_before is not None:
            log_cb(f"  ✓ Kredit awal: {credits_before}")
            if credits_before == 0:
                log_cb(
                    "[KREDIT] Kredit = 0! Profile ini tidak bisa create.\n"
                    "[KREDIT] Bulk: lanjut ke profile berikutnya. Single: dibatalkan."
                )
                if finish_cb:
                    try: finish_cb(0, 0, 0)
                    except Exception: pass
                return
        else:
            log_cb("  ⚠ Kredit awal tidak terbaca — validasi sukses akan dinonaktifkan.")

        _ar_max_retry = 3   # maks relaunch per sesi
        _ar_retry_count = 0

        for idx, song_config in enumerate(songs, 1):
            if is_stop_requested():
                log_cb(f"\n[STOP] Dihentikan. {songs_generated}/{quantity} berhasil.")
                break
            if is_paused():
                log_cb("[⏸ PAUSE] Dijeda — Chrome tetap buka. Klik Lanjutkan untuk melanjutkan.")
                wait_if_paused()
                if is_stop_requested():
                    break
                log_cb("[▶ LANJUT] Automation dilanjutkan.")

            # ── Auto-reopen: coba generate, kalau browser mati → relaunch ──
            title = None
            _song_done = False
            while not _song_done and not is_stop_requested():
                try:
                    # Cek browser masih hidup sebelum generate
                    _alive = False
                    try:
                        _alive = (context.browser is not None and context.browser.is_connected())
                    except Exception:
                        _alive = False

                    if not _alive:
                        raise Exception("Browser disconnected before generate")

                    title = await _generate_one_song(context, song_config, idx, quantity, log_cb)
                    _song_done = True  # berhasil (walau title None/gagal)

                except Exception as _br_err:
                    _err_s = str(_br_err).lower()
                    _is_crash = any(k in _err_s for k in [
                        "target page, context or browser has been closed",
                        "browser disconnected",
                        "browser has been closed",
                        "connection closed",
                        "disconnected",
                        "target closed",
                    ])
                    if not _is_crash or _ar_retry_count >= _ar_max_retry:
                        if not _is_crash:
                            log_cb(f"  [ERROR] Generate lagu {idx}: {str(_br_err)[:120]}")
                        else:
                            log_cb(f"\n[AUTO-REOPEN] ❌ Gagal relaunch {_ar_max_retry}x — generate dihentikan.")
                        _song_done = True  # skip lagu ini, lanjut
                        break

                    _ar_retry_count += 1
                    log_cb(f"\n[AUTO-REOPEN] Chrome crash/ditutup terdeteksi! (attempt {_ar_retry_count}/{_ar_max_retry})")
                    log_cb(f"[AUTO-REOPEN] Relaunch Chrome dalam 5s...")
                    await asyncio.sleep(5)

                    try:
                        # Tutup context lama kalau masih ada
                        try:
                            await context.close()
                        except Exception:
                            pass

                        # Relaunch Chrome baru
                        _new_managed = _launch_context(_ar_chrome_path, _ar_profile_dir, log_cb)
                        context = await _new_managed.__aenter__()
                        log_cb(f"[AUTO-REOPEN] Chrome berhasil dibuka ulang!")

                        # Verifikasi login ulang
                        _rp = context.pages[0] if context.pages else await context.new_page()
                        try:
                            await _rp.goto("https://suno.com/create", wait_until="commit", timeout=35000)
                            await asyncio.sleep(3)
                            if "/sign-in" in _rp.url or "/login" in _rp.url:
                                log_cb("[AUTO-REOPEN] ⚠ Perlu login ulang di browser!")
                        except Exception:
                            pass
                        log_cb(f"[AUTO-REOPEN] ✅ Lanjut dari lagu {idx}/{quantity}")

                    except Exception as _re_err:
                        log_cb(f"[AUTO-REOPEN] Gagal relaunch: {str(_re_err)[:100]}")
                        _song_done = True
                        break

            if title == "NO_CREDIT":
                log_cb(
                    f"[KREDIT] Kredit habis pada lagu {idx}/{quantity}!\n"
                    f"[KREDIT] Bulk: profile ini dihentikan, lanjut berikutnya.\n"
                    f"[KREDIT] Sudah berhasil: {songs_generated} lagu."
                )
                break
            if title:
                log_cb(f"  ✓ Lagu {idx}/{quantity} berhasil dibuat: '{title}'")
                generated_titles.append(title)
                songs_generated += 1
                if done_cb:
                    done_cb()
                if idx < quantity and not is_stop_requested():
                    _cfg_w = load_app_config()
                    _wmin = _cfg_w.get("wait_between_min", 50)
                    _wmax = _cfg_w.get("wait_between_max", 100)
                    import random as _rand
                    _mu  = (_wmin + _wmax) / 2
                    _sig = max(1, (_wmax - _wmin) / 6)
                    wait_between = int(max(_wmin, min(_wmax, _rand.gauss(_mu, _sig))))
                    log_cb(f"\n[WAIT] Jeda {wait_between}s (gaussian {_wmin}–{_wmax}s) sebelum lagu berikutnya...")
                    for elapsed in range(0, wait_between, 10):
                        if is_stop_requested():
                            break
                        # Cek browser masih hidup selama jeda
                        try:
                            if not (context.browser is not None and context.browser.is_connected()):
                                log_cb(f"\n[AUTO-REOPEN] Chrome ditutup saat jeda! Skip sisa jeda, relaunch...")
                                break  # keluar dari jeda, loop while di iterasi berikut akan handle relaunch
                        except Exception:
                            break
                        log_cb(f"  {wait_between - elapsed}s lagi...")
                        await asyncio.sleep(10)

        if not is_stop_requested():
            log_cb(f"\n[DONE] {songs_generated}/{quantity} lagu berhasil digenerate!")

        if songs_generated > 0:
            wait_sec = load_app_config().get("wait_render_sec", 180)
            log_cb(f"\n[WAIT] Menunggu {wait_sec}s render di Suno...")
            for elapsed in range(0, wait_sec, 10):
                if is_stop_requested():
                    break
                log_cb(f"  Rendering... {wait_sec - elapsed}s tersisa")
                await asyncio.sleep(10)

        downloaded_files = 0
        if songs_generated > 0 and not is_stop_requested():
            dl_count = songs_generated * 2
            log_cb(f"\n[DL] Download {dl_count} lagu teratas dari browser yang sama...")
            # Kirim judul AI agar nama file akurat (expand a/b di dalam fungsi)
            _ai_song_titles = songs  # full dict dengan title_a, title_b, lyrics
            downloaded_files = await _download_top_n_in_context(
                context, dl_count, log_cb,
                description=config.get("description", ""),
                ai_titles=_ai_song_titles) or 0

        # ══════════════════════════════════════════════════════
        # CEK KREDIT AKHIR — satu kali setelah semua lagu selesai
        # Delay 10s agar Suno sempat sync kredit ke server
        # ══════════════════════════════════════════════════════
        log_cb("\n[KREDIT] Menunggu sinkronisasi kredit Suno (10s)...")
        await asyncio.sleep(10)
        log_cb("[KREDIT] Cek kredit akhir...")
        latest_credits = await _check_credits_in_context(context, log_cb)

        if latest_credits is not None and credits_before is not None:
            kredit_turun   = credits_before - latest_credits
            real_success   = kredit_turun // FREE_CREDITS_PER_CREATE
            sisa_kredit    = latest_credits
            bisa_download  = songs_generated  # jumlah yang akan didownload = yang berhasil diklik

            log_cb(f"\n{'='*50}")
            log_cb(f"[RINGKASAN] Hasil Generate:")
            log_cb(f"  Kredit awal       : {credits_before}")
            log_cb(f"  Kredit akhir      : {sisa_kredit}")
            log_cb(f"  Kredit terpakai   : {kredit_turun} ({kredit_turun // FREE_CREDITS_PER_CREATE} lagu × {FREE_CREDITS_PER_CREATE} kredit)")

            if real_success > 0 and real_success != songs_generated:
                log_cb(f"  Lagu sukses (kredit) : {real_success}")
                log_cb(f"  Lagu sukses (klik)   : {songs_generated}")
                log_cb(f"  ⚠ Selisih — pakai angka kredit sebagai acuan.")
                songs_generated = max(0, real_success)
            elif real_success == 0 and songs_generated > 0:
                log_cb(f"  Lagu sukses       : {songs_generated} (kredit belum sync — pakai data klik)")
            else:
                log_cb(f"  Lagu sukses       : {songs_generated} ✓")

            log_cb(f"  Siap didownload   : {songs_generated} lagu")
            log_cb(f"  Sisa kredit       : {sisa_kredit} (bisa buat {sisa_kredit // FREE_CREDITS_PER_CREATE} lagu lagi)")
            log_cb(f"{'='*50}")

        elif latest_credits is not None:
            log_cb(f"[KREDIT] Kredit saat ini: {latest_credits} (kredit awal tidak diketahui)")
            log_cb(f"[RINGKASAN] Lagu berhasil dibuat: {songs_generated}")
        else:
            log_cb("[KREDIT] ⚠ Kredit akhir tidak terbaca — sukses dihitung dari klik tombol.")
            log_cb(f"[RINGKASAN] Lagu berhasil dibuat: {songs_generated}")

        log_cb("\n[DONE] Semua selesai. Menutup browser...")
        try:
            await context.close()
        except Exception:
            pass

    if finish_cb:
        try:
            finish_cb(songs_generated, downloaded_files, latest_credits)
        except Exception as e:
            log_cb(f"[FINISH CALLBACK] Error: {e}")

def _release_profile_lock(profile_dir: str, log_cb=None) -> bool:
    """
    Hapus file lock Chrome di folder profile agar Playwright bisa launch
    tanpa harus kill process Chrome lain.
    File lock: SingletonLock, SingletonCookie, SingletonSocket, lockfile
    Return True jika ada file yang dihapus.
    """
    lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]
    removed = False
    profile_path = Path(profile_dir)
    for fname in lock_files:
        lock = profile_path / fname
        if lock.exists():
            try:
                lock.unlink()
                if log_cb:
                    log_cb(f"  [LOCK] Hapus {fname} dari profile {profile_path.name}")
                removed = True
            except Exception as e:
                if log_cb:
                    log_cb(f"  [LOCK] Gagal hapus {fname}: {e}")
    return removed




def _is_chrome_running_for_profile(profile_dir: str) -> bool:
    """FIX: Cek apakah Chrome sudah terbuka dengan profile ini."""
    import subprocess, sys
    profile_path = str(Path(profile_dir).resolve()).lower()
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["wmic", "process", "where", "name='chrome.exe'",
                 "get", "commandline", "/format:csv"],
                capture_output=True, text=True, timeout=10)
            return profile_path in r.stdout.lower()
        else:
            r = subprocess.run(["pgrep", "-af", "chrome"],
                               capture_output=True, text=True, timeout=5)
            return profile_path in r.stdout.lower()
    except Exception:
        return False


def _close_chrome_for_profile(profile_dir: str, log_cb=None) -> bool:
    """FIX: Tutup paksa Chrome yang sedang memakai profile ini."""
    import subprocess, time, sys
    profile_path = str(Path(profile_dir).resolve()).lower()
    killed = False
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["wmic", "process", "where", "name='chrome.exe'",
                 "get", "processid,commandline", "/format:csv"],
                capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                if profile_path in line.lower():
                    parts = line.split(",")
                    pid = parts[-1].strip() if parts else ""
                    if pid.isdigit():
                        subprocess.run(["taskkill", "/PID", pid, "/F"],
                                       capture_output=True, timeout=5)
                        if log_cb:
                            log_cb(f"  [LAUNCH] Tutup Chrome PID {pid}")
                        killed = True
        else:
            r = subprocess.run(["pgrep", "-af", "chrome"],
                               capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if profile_path in line.lower():
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        subprocess.run(["kill", "-9", parts[0]],
                                       capture_output=True, timeout=5)
                        killed = True
        if killed:
            time.sleep(2)
            _release_profile_lock(profile_dir, log_cb)
    except Exception as e:
        if log_cb:
            log_cb(f"  [LAUNCH] Gagal tutup Chrome: {e}")
    return killed

def _get_profile_browser_cfg(profile_dir: str) -> dict:
    """Baca/buat config browser per-profile dari browser_cfg.json.
    UA + window size di-random SEKALI lalu disimpan — tidak berubah tiap launch.
    """
    import json as _j, random as _r
    cfg_path = Path(profile_dir) / "browser_cfg.json"
    if cfg_path.exists():
        try:
            cfg = _j.loads(cfg_path.read_text(encoding="utf-8"))
            if cfg.get("width") and cfg.get("height") and cfg.get("user_agent"):
                return cfg
        except Exception:
            pass
    _sizes = [(1366, 768)]  # Fixed 1366×768 — mudah dilihat di semua resolusi
    _tzs   = ["Asia/Jakarta","Asia/Makassar","Asia/Jayapura","Asia/Singapore","Asia/Kuala_Lumpur"]
    _cvs   = ["130.0.0.0","131.0.0.0","132.0.0.0","133.0.0.0","134.0.0.0","135.0.0.0","136.0.0.0"]
    _plats = [
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
        ("Macintosh; Intel Mac OS X 12_6_0",  "macOS"),
        ("Macintosh; Intel Mac OS X 13_5_0",  "macOS"),
    ]
    cv = _r.choice(_cvs); plat, _os_name = _r.choice(_plats)
    ua = f"Mozilla/5.0 ({plat}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cv} Safari/537.36"
    w, h = _r.choice(_sizes); tz = _r.choice(_tzs)
    cfg = {"user_agent": ua, "width": w, "height": h, "timezone": tz,
           "os": _os_name, "spoof_2k_screen": True}
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(_j.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return cfg


def _random_browser_profile(profile_dir: str = "") -> dict:
    """
    Generate random user-agent, window size, dan locale untuk anti-fingerprint.
    FIX#8a:
    - UA pool diperluas: Windows 10/11 + macOS (lebih susah dideteksi)
    - Chrome versi update ke April 2026 (134-136)
    - Viewport MAX 1920x1080 agar user bisa klik manual captcha di layar FHD
    - screen_2k=True → JS override screen.width/height ke 2560x1440
      sehingga UA mengiklankan layar 2K tapi rendering tetap FHD
    """
    # FIX: jika profile_dir diberikan → pakai config persisten per-profile
    if profile_dir:
        return _get_profile_browser_cfg(profile_dir)

    import random

    # Chrome versi terkini April 2026
    chrome_versions = [
        "130.0.0.0", "131.0.0.0", "132.0.0.0",
        "133.0.0.0", "134.0.0.0", "135.0.0.0", "136.0.0.0",
    ]

    # Pool platform: campuran Windows 10/11 + macOS (lebih human-like)
    platforms = [
        # Windows 10
        ("Windows NT 10.0; Win64; x64", "Windows"),
        ("Windows NT 10.0; Win64; x64", "Windows"),  # 2x agar lebih sering
        # Windows 11 (NT masih 10.0 di UA string)
        ("Windows NT 10.0; Win64; x64", "Windows"),
        # macOS (Monterey / Ventura / Sonoma)
        ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
        ("Macintosh; Intel Mac OS X 11_6_0",  "macOS"),
        ("Macintosh; Intel Mac OS X 12_6_0",  "macOS"),
        ("Macintosh; Intel Mac OS X 13_5_0",  "macOS"),
        ("Macintosh; Intel Mac OS X 14_0",    "macOS"),
    ]
    cv        = random.choice(chrome_versions)
    plat, _os = random.choice(platforms)
    ua = (
        f"Mozilla/5.0 ({plat}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{cv} Safari/537.36"
    )

    # FIX#8a — Viewport tetap FHD agar user bisa klik captcha manual
    # (tidak melebihi layar fisik 1920x1080)
    # screen.width/height akan di-spoof ke 2560x1440 via JS init script
    sizes_fhd = [(1366, 768)]  # Fixed 1366×768
    w, h = random.choice(sizes_fhd)

    # Random timezone
    timezones = [
        "Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura",
        "Asia/Singapore", "Asia/Kuala_Lumpur",
    ]
    tz = random.choice(timezones)

    return {
        "user_agent": ua,
        "width":      w,
        "height":     h,
        "timezone":   tz,
        "os":         _os,
        # Flag: spoof screen ke 2K via JS (tidak ubah viewport fisik)
        "spoof_2k_screen": True,
    }


async def _launch_context(chrome_path, profile_dir, log_cb=None):
    """
    Mengembalikan async context manager yang membungkus Playwright + BrowserContext.
    Menggunakan pola yang benar agar __aexit__ tidak error.
    """
    from playwright.async_api import async_playwright
    import asyncio

    # FIX: Cek apakah Chrome sudah terbuka dengan profile ini → tutup otomatis
    if _is_chrome_running_for_profile(profile_dir):
        if log_cb:
            log_cb("  [LAUNCH] Chrome sudah terbuka dengan profile ini!")
            log_cb("  [LAUNCH] Menutup Chrome otomatis agar bot bisa launch...")
        closed = _close_chrome_for_profile(profile_dir, log_cb)
        if not closed:
            if log_cb:
                log_cb("  [LAUNCH] Auto-close gagal, hapus lock file saja...")
            _release_profile_lock(profile_dir, log_cb)
    else:
        _release_profile_lock(profile_dir, log_cb)

    _rt_cfg   = load_app_config()
    _headless = _rt_cfg.get("headless", False)
    _slow_mo  = 0 if _headless else 60
    if log_cb and _headless:
        log_cb("  [LAUNCH] Mode: HEADLESS — Chrome berjalan di background")

    class _ManagedCtx:
        """Wrapper context manager yang handle lifecycle Playwright + BrowserContext."""
        def __init__(self):
            self._pw_ctx_mgr = None  # async_playwright() context manager
            self._pw         = None  # Playwright instance
            self._context    = None  # BrowserContext

        async def __aenter__(self):
            self._pw_ctx_mgr = async_playwright()
            self._pw = await self._pw_ctx_mgr.__aenter__()

            # FIX: Fingerprint persisten per-profile (tidak acak tiap launch)
            _bp = _random_browser_profile(str(profile_dir))
            # Override resolusi dari Runtime Settings (user bisa pilih di UI)
            _rt_ws = load_app_config().get("window_size", "1366x768")
            try:
                _ow, _oh = [int(x) for x in _rt_ws.lower().split("x")]
                _bp["width"]  = _ow
                _bp["height"] = _oh
            except Exception:
                _bp["width"], _bp["height"] = 1366, 768
            if log_cb:
                log_cb(f"  [LAUNCH] Fingerprint: {_bp['width']}x{_bp['height']} | {_bp['timezone']} (resolusi dari Runtime Settings)")

            # Posisi window dari sesi terakhir untuk profile ini
            _win_pos = load_window_position(str(profile_dir))
            _pos_x, _pos_y = (_win_pos if _win_pos else (80, 80))

            # Tentukan args berdasarkan window_mode
            _win_mode = _rt_cfg.get("window_mode", "normal")
            _launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run", "--no-default-browser-check",
                "--disable-gpu",
                "--disable-gpu-sandbox",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                f"--window-size={_bp['width']},{_bp['height']}",
                f"--window-position={_pos_x},{_pos_y}",
            ]
            if _win_mode == "background":
                if log_cb:
                    log_cb("  [LAUNCH] Mode: BACKGROUND — Chrome akan diminimize otomatis")

            try:
                self._context = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    executable_path=chrome_path,
                    headless=_headless,
                    slow_mo=_slow_mo,
                    args=_launch_args,
                    user_agent=_bp["user_agent"],
                    viewport={"width": _bp["width"], "height": _bp["height"]},
                    locale="en-US",
                    timezone_id=_bp["timezone"],
                )
            except Exception as e:
                err_msg = str(e)
                if ("Browser window not found" in err_msg
                        or "already running" in err_msg.lower()
                        or "connect" in err_msg.lower()
                        or "target" in err_msg.lower()):
                    if log_cb:
                        log_cb("  [LAUNCH] Browser gagal launch — force-kill + retry...")
                    # Force kill Chrome untuk profile ini
                    _close_chrome_for_profile(profile_dir, log_cb)
                    # Hapus lock file eksplisit
                    _release_profile_lock(profile_dir, log_cb)
                    for _singleton in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
                        _sl = Path(profile_dir) / _singleton
                        try:
                            if _sl.exists():
                                _sl.unlink()
                                if log_cb:
                                    log_cb(f"  [LAUNCH] Hapus {_singleton}")
                        except Exception:
                            pass
                    # FIX: Retry 3x — hapus duplikat args, retry-3 fallback headless=True
                    _last_err = e
                    _DUP_FLAGS = {"--disable-gpu", "--disable-gpu-sandbox",
                                  "--disable-software-rasterizer", "--disable-dev-shm-usage",
                                  "--no-sandbox"}
                    _clean_args = [
                        a for a in _launch_args
                        if not any(a.startswith(d) for d in _DUP_FLAGS)
                        and not a.startswith("--window-position")
                    ]
                    for _attempt in range(1, 4):
                        await asyncio.sleep(_attempt * 3)
                        if log_cb:
                            log_cb(f"  [LAUNCH] Retry {_attempt}/3...")
                        _close_chrome_for_profile(profile_dir, log_cb)
                        _release_profile_lock(profile_dir, log_cb)
                        await asyncio.sleep(1)
                        _hl_retry = True if _attempt == 3 else _headless
                        if _attempt == 3 and log_cb:
                            log_cb("  [LAUNCH] Retry 3 → fallback headless mode...")
                        try:
                            self._context = await self._pw.chromium.launch_persistent_context(
                                user_data_dir=profile_dir,
                                executable_path=chrome_path,
                                headless=_hl_retry,
                                slow_mo=_slow_mo,
                                args=_clean_args,
                                user_agent=_bp["user_agent"],
                                viewport={"width": _bp["width"], "height": _bp["height"]},
                                locale="en-US",
                                timezone_id=_bp["timezone"],
                            )
                            if log_cb:
                                log_cb(f"  [LAUNCH] ✓ Berhasil di retry {_attempt}")
                            _last_err = None
                            break
                        except Exception as _re:
                            _last_err = _re
                            if log_cb:
                                log_cb(f"  [LAUNCH] Retry {_attempt} gagal: {_re.__class__.__name__}")
                    if _last_err is not None:
                        await self._pw_ctx_mgr.__aexit__(None, None, None)
                        raise _last_err
                else:
                    await self._pw_ctx_mgr.__aexit__(None, None, None)
                    raise
            # FIX: Tunggu browser benar-benar siap sebelum inject & navigasi
            await asyncio.sleep(1.5)  # beri waktu Chrome startup
            try:
                _pages = self._context.pages
                if _pages:
                    try:
                        await _pages[0].wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass  # timeout OK, browser tetap bisa dipakai
                else:
                    _blank = await self._context.new_page()
                    try:
                        await _blank.goto("about:blank", timeout=5000)
                    except Exception:
                        pass
            except Exception:
                pass

            # FIX#8b: spoof screen ke 2560x1440 (2K) via JS agar UA konsisten
            #         meski viewport fisik tetap FHD (agar bisa klik captcha manual)
            # Gunakan resolusi dari Runtime Settings (sudah di-override di _bp)
            _screen_w = _bp["width"]
            _screen_h = _bp["height"]
            _os_name  = _bp.get("os", "Windows")
            await self._context.add_init_script(f"""
                // Anti-detect: sembunyikan WebDriver
                Object.defineProperty(navigator,'webdriver',{{get:()=>undefined}});
                // Plugin list (non-empty = tampak human)
                Object.defineProperty(navigator,'plugins',{{get:()=>[1,2,3,4,5]}});
                // Language
                Object.defineProperty(navigator,'languages',{{get:()=>['en-US','en']}});
                // Chrome runtime
                window.chrome={{runtime:{{}}}};
                // Permissions
                Object.defineProperty(navigator,'permissions',{{
                    get:()=>{{return {{query:()=>Promise.resolve({{state:'granted'}})}};}}
                }});
                // FIX#8b: Spoof screen size ke {_screen_w}x{_screen_h}
                Object.defineProperty(screen,'width',  {{get:()=>{_screen_w}}});
                Object.defineProperty(screen,'height', {{get:()=>{_screen_h}}});
                Object.defineProperty(screen,'availWidth',  {{get:()=>{_screen_w}}});
                Object.defineProperty(screen,'availHeight', {{get:()=>{_screen_h - 40}}});
                Object.defineProperty(window,'outerWidth',  {{get:()=>{_screen_w}}});
                Object.defineProperty(window,'outerHeight', {{get:()=>{_screen_h}}});
                // Platform
                Object.defineProperty(navigator,'platform',
                    {{get:()=>'{("Win32" if _os_name == "Windows" else "MacIntel")}'}});
                // Hardware concurrency (bervariasi)
                Object.defineProperty(navigator,'hardwareConcurrency',{{get:()=>8}});
                // Device memory
                Object.defineProperty(navigator,'deviceMemory',{{get:()=>8}});
            """)
            # Background mode: minimize Chrome setelah launch
            if _win_mode == "background":
                await asyncio.sleep(1.5)  # Tunggu window Chrome benar-benar muncul
                _minimize_chrome_windows()
            return self._context

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            # FIX: Simpan posisi window Chrome sebelum ditutup
            try:
                if self._context:
                    _pgs = self._context.pages
                    if _pgs:
                        _b = await _pgs[0].evaluate(
                            "()=>({x:window.screenX||window.screenLeft||0,"
                            "y:window.screenY||window.screenTop||0})"
                        )
                        _wx = int(_b.get("x", 0)); _wy = int(_b.get("y", 0))
                        if _wx >= 0 and _wy >= 0:
                            save_window_position(str(profile_dir), _wx, _wy)
            except Exception:
                pass
            try:
                if self._context:
                    await self._context.close()
            except Exception:
                pass
            try:
                if self._pw_ctx_mgr:
                    await self._pw_ctx_mgr.__aexit__(None, None, None)
            except Exception:
                pass
            return False  # tidak suppress exception

        # Proxy: allow "async with (await _launch_context(...)) as ctx"
        # maupun "async with _launch_context(...) as ctx"
        def __await__(self):
            async def _passthrough():
                return self
            return _passthrough().__await__()

        def __getattr__(self, name):
            if self._context is not None:
                return getattr(self._context, name)
            raise AttributeError(name)

    return _ManagedCtx()


# ------------------------------------------------------------------
# Scrape judul lagu dari halaman Suno
# ------------------------------------------------------------------

# Kata-kata yang BUKAN judul lagu (UI element Suno)
_SUNO_UI_NOISE = {
    "suno", "create", "library", "home", "explore", "trending",
    "frequently used", "recently used", "recently played",
    "sign in", "log in", "sign up", "upload", "download",
    "settings", "profile", "account", "billing", "subscription",
    "search", "discover", "feed", "following", "likes",
    "playlists", "albums", "artists", "genres",
}


async def _get_song_title_from_page(page) -> str:
    """
    Ambil judul lagu dari halaman Suno song page.
    Prioritas: og:title > document title > og:description > aria-label spesifik
    """
    # 1. og:title — paling akurat, berisi judul lagu langsung
    try:
        el = await page.query_selector("meta[property='og:title']")
        if el:
            val = (await el.get_attribute("content") or "").strip()
            if val and val.lower() not in _SUNO_UI_NOISE and len(val) > 1:
                # og:title format biasanya "Song Title | Suno" atau hanya "Song Title"
                if " | " in val:
                    val = val.split(" | ")[0].strip()
                if val and val.lower() not in _SUNO_UI_NOISE:
                    return val
    except Exception:
        pass

    # 2. Document title — format "Song Title | Suno" atau "Song Title - Suno"
    try:
        title = await page.title()
        if title:
            for sep in [" | ", " - ", " – "]:
                if sep in title:
                    part = title.split(sep)[0].strip()
                    if part and part.lower() not in _SUNO_UI_NOISE and len(part) > 1:
                        return part
            # Kalau tidak ada separator tapi bukan noise
            if title.lower() not in _SUNO_UI_NOISE and len(title) > 1:
                return title.strip()
    except Exception:
        pass

    # 3. og:description — kadang berisi nama lagu
    try:
        el = await page.query_selector("meta[name='description'], meta[property='og:description']")
        if el:
            val = (await el.get_attribute("content") or "").strip()
            # Ambil bagian pertama sebelum tanda baca panjang
            first = val.split(".")[0].split(",")[0].strip()
            if first and first.lower() not in _SUNO_UI_NOISE and 2 < len(first) < 80:
                return first
    except Exception:
        pass

    return ""




# ------------------------------------------------------------------
# Captcha detection & handler
# ------------------------------------------------------------------

async def _check_and_handle_captcha(page, log_cb, profile_name: str = "") -> bool:
    """
    PATCH: Deteksi captcha/challenge pada halaman Suno.
    Metode deteksi diperluas:
      1. Selector DOM (iframe CF/hCaptcha/reCaptcha, class, id, cf-turnstile, dll)
      2. Page title ("just a moment", "attention required", "security check", "verify")
      3. URL mengandung /cdn-cgi/challenge atau /checkpoint
      4. Body text mengandung "verify you are human", "checking your browser", dll
      5. Elemen teks di halaman ("Verifying you are human", "DDoS protection")
    Return True  = tidak ada captcha / sudah selesai → lanjut normal
    Return False = captcha timeout / skip
    """
    import asyncio

    _rt_cfg = load_app_config()
    action  = _rt_cfg.get("captcha_action", "pause")
    timeout = _rt_cfg.get("captcha_timeout_sec", 120)

    captcha_selectors = [
        "iframe[src*='challenges.cloudflare.com' i]",
        "iframe[src*='hcaptcha.com' i]",
        "iframe[src*='recaptcha' i]",
        "iframe[title*='challenge' i]",
        "iframe[title*='captcha' i]",
        "[class*='captcha' i]",
        "[id*='captcha' i]",
        "[data-testid*='captcha' i]",
        "div.cf-turnstile",
        "#challenge-running",
        "#challenge-form",
        "#cf-challenge-running",
        "[data-ray]",
        "div.hcaptcha-box",
        "text=verify you are human",
        "text=press hold",
        "text=complete the security check",
    ]
    captcha_found = False

    # Cek 1: selector DOM
    for sel in captcha_selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                captcha_found = True
                log_cb(f"  [CAPTCHA] Terdeteksi via selector: {sel}")
                break
        except Exception:
            continue

    # Cek 2: page title
    if not captcha_found:
        try:
            title = (await page.title()).lower()
            captcha_keywords_title = [
                "just a moment", "attention required", "security check",
                "verify", "checking your browser", "ddos protection",
                "cloudflare", "access denied"
            ]
            for kw in captcha_keywords_title:
                if kw in title:
                    captcha_found = True
                    log_cb(f"  [CAPTCHA] Terdeteksi via title: '{title[:60]}'")
                    break
        except Exception:
            pass

    # Cek 3: URL
    if not captcha_found:
        try:
            current_url = page.url.lower()
            if any(p in current_url for p in [
                "/cdn-cgi/challenge", "/checkpoint", "cf_chl", "cloudflare"
            ]):
                captcha_found = True
                log_cb(f"  [CAPTCHA] Terdeteksi via URL: {page.url[:80]}")
        except Exception:
            pass

    # Cek 4: body text
    if not captcha_found:
        try:
            body = (await page.inner_text("body"))[:1000].lower()
            captcha_keywords_body = [
                "verify you are human", "checking your browser",
                "ddos protection", "security check", "please wait",
                "enable javascript and cookies", "ray id",
                "verifying you are human", "just a moment"
            ]
            for kw in captcha_keywords_body:
                if kw in body:
                    captcha_found = True
                    log_cb(f"  [CAPTCHA] Terdeteksi via body text: '{kw}'")
                    break
        except Exception:
            pass

    # Lapis 5: frame_locator masuk ke iframe Cloudflare
    if not captcha_found:
        try:
            _cf_frame = page.frame_locator("iframe[src*='challenges.cloudflare.com' i]").first
            _btn = _cf_frame.locator("text=verify you are human").first
            if await _btn.count() > 0 and await _btn.is_visible(timeout=500):
                captcha_found = True
                log_cb("  [CAPTCHA] Terdeteksi via frame_locator Cloudflare")
        except Exception:
            pass

    if not captcha_found:
        return True  # Tidak ada captcha, lanjut normal

    label = f" [{profile_name}]" if profile_name else ""
    log_cb(f"  ⚠️ CAPTCHA TERDETEKSI{label}!")

    if action == "skip":
        log_cb("=" * 52)
        log_cb(f"  ⚠ CAPTCHA TERDETEKSI — Profile: [{profile_name}]")
        log_cb("  ⏭ Setting: SKIP — profile ini dilewati otomatis.")
        log_cb("  ➡ Buka Chrome manual → solve CAPTCHA → coba lagi.")
        log_cb("=" * 52)
        try:
            import winsound as _ws
            for _ in range(3):
                _ws.Beep(1400, 300)
                import time as _tt; _tt.sleep(0.15)
        except Exception:
            try:
                import subprocess
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command",
                     "[console]::beep(1400,300);Start-Sleep -m 150;"
                     "[console]::beep(1400,300);Start-Sleep -m 150;"
                     "[console]::beep(1400,300)"],
                    creationflags=0x08000000
                )
            except Exception:
                pass
        try:
            import ctypes, ctypes.wintypes
            class _FWI(ctypes.Structure):
                _fields_ = [("cbSize",ctypes.c_uint),("hwnd",ctypes.wintypes.HWND),
                             ("dwFlags",ctypes.c_uint),("uCount",ctypes.c_uint),
                             ("dwTimeout",ctypes.c_uint)]
            _hl = []
            _WEP = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def _ecb(hwnd, _):
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                t = buf.value.lower()
                if "asugen" in t or "suno" in t: _hl.append(hwnd)
                return True
            ctypes.windll.user32.EnumWindows(_WEP(_ecb), 0)
            for _hw in _hl:
                fi = _FWI(ctypes.sizeof(_FWI), _hw, 0x0F, 10, 0)
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
        except Exception:
            pass
        try:
            _ps = load_profiles()
            for _p in _ps:
                if _p.get("name","") == profile_name or profile_name in _p.get("profile_dir",""):
                    _p["status_info"] = "⚠ CAPTCHA — skip"
                    break
            save_profiles(_ps)
        except Exception:
            pass
        return False

    # action == "pause": tampilkan notif dan tunggu user solve
    log_cb(f"  ⏸ Browser dibiarkan terbuka. Selesaikan captcha dalam {timeout} detik...")
    log_cb("  Setelah captcha selesai, script otomatis lanjut.")

    # Restore + bawa browser ke foreground agar user bisa lihat captcha
    try:
        await page.bring_to_front()
    except Exception:
        pass

    # Restore window Chrome yang mungkin sedang minimize
    try:
        import ctypes, ctypes.wintypes
        SW_RESTORE = 9
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _restore_cb(hwnd, _):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                t = buf.value.lower()
                if "chrome" in t or "chromium" in t or "suno" in t:
                    ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
        ctypes.windll.user32.EnumWindows(WNDENUMPROC(_restore_cb), 0)
    except Exception:
        pass

    # FIX: Beep agresif — burst 3 nada, ulang tiap 5 detik selama ~60 detik
    def _play_alert():
        try:
            import winsound, time
            for _ in range(12):
                try:
                    winsound.Beep(1500, 250); time.sleep(0.08)
                    winsound.Beep(900,  250); time.sleep(0.08)
                    winsound.Beep(1500, 400)
                except Exception:
                    pass
                time.sleep(5)
        except Exception:
            try:
                import subprocess, time
                for _ in range(6):
                    subprocess.Popen(
                        ["powershell", "-WindowStyle", "Hidden", "-Command",
                         "[console]::beep(1200,250);[console]::beep(800,250);[console]::beep(1200,400)"],
                        creationflags=0x08000000
                    )
                    time.sleep(5)
            except Exception:
                pass
    import threading as _thr
    _thr.Thread(target=_play_alert, daemon=True).start()

    # Popup Tkinter topmost + flash taskbar
    def _show_captcha_popup():
        try:
            # ctypes MessageBoxW - aman dipanggil dari thread mana saja, tidak butuh Tkinter
            import ctypes
            _msg = (
                f"Profile: {profile_name}\n\n"
                "Suno menampilkan CAPTCHA di Chrome!\n"
                "Segera buka Chrome dan selesaikan CAPTCHA.\n\n"
                f"Timeout: {timeout} detik\n"
                "Script otomatis lanjut setelah CAPTCHA selesai."
            )
            MB_ICONWARNING = 0x30
            MB_SYSTEMMODAL = 0x1000
            MB_TOPMOST     = 0x40000
            ctypes.windll.user32.MessageBoxW(
                0, _msg, "⚠ CAPTCHA TERDETEKSI — ASuGen",
                MB_ICONWARNING | MB_SYSTEMMODAL | MB_TOPMOST
            )
        except Exception:
            pass
    _thr.Thread(target=_show_captcha_popup, daemon=True).start()

    # Windows Toast Notification via PowerShell (notif system tray)
    def _show_toast():
        try:
            import subprocess
            _msg = f"Profile: {profile_name} - Selesaikan CAPTCHA di Chrome!"
            _ps_toast = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Warning;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(20000,'ASuGen - CAPTCHA!','{_msg}',"
                "[System.Windows.Forms.ToolTipIcon]::Warning);"
                "Start-Sleep 21;$n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command", _ps_toast],
                creationflags=0x08000000
            )
        except Exception:
            pass
        try:
            import ctypes, ctypes.wintypes
            class _FWIX(ctypes.Structure):
                _fields_ = [("cbSize",ctypes.c_uint),("hwnd",ctypes.wintypes.HWND),
                             ("dwFlags",ctypes.c_uint),("uCount",ctypes.c_uint),
                             ("dwTimeout",ctypes.c_uint)]
            _hlx = []
            _WENP = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def _ecbx(hwnd, _):
                buf = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                t = buf.value.lower()
                if "asugen" in t or "suno" in t: _hlx.append(hwnd)
                return True
            ctypes.windll.user32.EnumWindows(_WENP(_ecbx), 0)
            for _hw in _hlx:
                fi = _FWIX(ctypes.sizeof(_FWIX), _hw, 0x0F, 15, 0)
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
        except Exception:
            pass
    _thr.Thread(target=_show_toast, daemon=True).start()

    # Tunggu hingga captcha hilang atau timeout
    elapsed = 0
    interval = 3
    while elapsed < timeout:
        await asyncio.sleep(interval)
        elapsed += interval
        still_captcha = False
        for sel in captcha_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    still_captcha = True
                    break
            except Exception:
                continue
        try:
            title = (await page.title()).lower()
            if "just a moment" in title or "attention required" in title:
                still_captcha = True
        except Exception:
            pass
        if not still_captcha:
            log_cb("  ✅ Captcha selesai! Melanjutkan...")
            return True
        remaining = timeout - elapsed
        if remaining > 0 and elapsed % 15 == 0:
            log_cb(f"  ⏳ Menunggu captcha... sisa {remaining}s")

    log_cb(f"  ❌ Timeout {timeout}s — captcha tidak selesai. Profile di-skip.")
    if profile_name:
        try:
            _ps_t = load_profiles()
            for _p_t in _ps_t:
                if _p_t.get("name","") == profile_name or profile_name in _p_t.get("profile_dir",""):
                    _p_t["status_info"] = f"⚠ CAPTCHA (timeout {timeout}s)"
                    break
            save_profiles(_ps_t)
        except Exception:
            pass
    return False

# ------------------------------------------------------------------
# Cek kredit Suno — buka browser, baca dari tampilan halaman
# ------------------------------------------------------------------

def run_check_credits(chrome_path: str, profile_dir: str, log_cb, result_cb=None, auto_close=True):
    profile_dir = resolve_profile_dir(profile_dir)  # FIX portable path
    import asyncio
    try:
        _run_async(_async_check_credits(chrome_path, profile_dir, log_cb, result_cb, auto_close=auto_close))
    except Exception as e:
        log_cb(f"ERROR cek kredit: {e.__class__.__name__}: {str(e)[:120]}")
        log_cb("  [LAUNCH] Pastikan Chrome sudah tertutup sebelum cek kredit.")
        # Force kill Chrome untuk profile ini supaya cek berikutnya bisa jalan
        _close_chrome_for_profile(profile_dir, log_cb)
        _release_profile_lock(profile_dir, log_cb)
        import time; time.sleep(2)
        if result_cb:
            result_cb(None)


async def _async_check_credits(chrome_path: str, profile_dir: str, log_cb, result_cb, auto_close=True):
    """
    _stop_ev = get_stop_event()   # FIX: stop singleton
    Buka browser, navigasi ke Suno, baca kredit langsung dari tampilan halaman.
    Murni DOM scan — tidak pakai API/intercept/fetch.
    """
    import asyncio

    log_cb("[KREDIT] Membuka browser...")
    credits = None

    async with (await _launch_context(chrome_path, profile_dir, log_cb)) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        # Buka halaman dengan retry - toleran terhadap timeout & blank page
        _URLS_TO_TRY = ["https://suno.com/create", "https://suno.com", "https://suno.com/account"]
        _goto_ok = False
        for _url_try in _URLS_TO_TRY:
            log_cb(f"[KREDIT] Buka {_url_try}...")
            try:
                await page.goto(_url_try, wait_until="commit", timeout=35000)
                await asyncio.sleep(2)
                _cur = page.url
                if "about:blank" not in _cur and "chrome-error" not in _cur:
                    _goto_ok = True
                    log_cb(f"  OK: Halaman terbuka ({_cur[:60]})")
                    break
                else:
                    log_cb("  Masih blank, coba URL berikutnya...")
            except Exception as e:
                log_cb(f"  warning goto {_url_try}: {str(e)[:80]}")

        if not _goto_ok:
            log_cb("  ❌ Semua URL gagal dibuka. Cek koneksi internet / Suno mungkin down.")
            if result_cb:
                result_cb(None)
            return

        # Tunggu halaman selesai load
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        _loaded = False
        for _w in range(25):  # polling max 25s
            await asyncio.sleep(1)
            _cur_url = page.url
            if "/sign-in" in _cur_url or "/login" in _cur_url:
                break
            if "about:blank" in _cur_url or "chrome-error" in _cur_url:
                if _w == 10:
                    try:
                        await page.goto("https://suno.com", wait_until="commit", timeout=20000)
                    except Exception:
                        pass
                continue
            _body = ""
            try:
                _body = await page.inner_text("body")
            except Exception:
                pass
            if any(kw in _body.lower() for kw in ["credits", "credit", "remaining", "balance"]):
                _loaded = True
                log_cb(f"  OK: Konten kredit terdeteksi ({_w+1}s)")
                break
            if _w == 5:
                log_cb("  Menunggu halaman selesai loading...")
            if _w == 15:
                log_cb("  Masih loading, harap tunggu...")
        if not _loaded:
            log_cb("  Halaman ter-load (timeout tunggu kredit — tetap coba scan).")

        # Cek login
        if "/sign-in" in page.url or "/login" in page.url:
            log_cb("  GAGAL: Belum login! Gunakan 'Open Selected' untuk login dulu.")
            if result_cb:
                result_cb(None)
            return

        log_cb("  OK: Mencari angka kredit...")

        # Step 1: Scan body text langsung
        credits = await _scan_page_for_credits(page, log_cb)

        # Step 2: Coba klik avatar/profile untuk buka dropdown
        if not credits:
            log_cb("  Coba buka profile menu...")
            for sel in [
                "button[class*='avatar' i]", "img[class*='avatar' i]",
                "[class*='Avatar']", "[data-testid*='avatar']", "[data-testid*='user']",
                "[aria-label*='account' i]", "[aria-label*='profile' i]", "[aria-label*='user' i]",
                "button[class*='User']", "button[class*='Profile']",
                "nav button:last-child", "header button:last-child",
            ]:
                try:
                    el = await page.wait_for_selector(sel, timeout=1500, state="visible")
                    if el:
                        await el.click()
                        await asyncio.sleep(2)
                        log_cb(f"  Klik: {sel}")
                        credits = await _scan_page_for_credits(page, log_cb)
                        if credits:
                            break
                        await page.keyboard.press("Escape")
                        await asyncio.sleep(0.5)
                except Exception:
                    continue

        # Step 3: Coba halaman account/billing dengan polling
        if not credits:
            for url in ["https://suno.com/account", "https://suno.com/billing"]:
                log_cb(f"  Coba halaman: {url}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    # FIX: polling tunggu kredit muncul
                    for _w3 in range(10):
                        await asyncio.sleep(1)
                        _b3 = ""
                        try:
                            _b3 = await page.inner_text("body")
                        except Exception:
                            pass
                        if any(kw in _b3.lower() for kw in ["credits", "credit", "remaining", "balance"]):
                            break
                    credits = await _scan_page_for_credits(page, log_cb)
                    if credits:
                        break
                except Exception:
                    continue

        # Hasil
        if credits:
            log_cb(f"[KREDIT] \u2713 Kredit: {credits}")
        else:
            log_cb("[KREDIT] Tidak berhasil baca kredit otomatis.")
            log_cb("  Lihat langsung di browser \u2014 angka kredit ada di pojok kanan atas Suno.")
            try:
                shot = SONGS_DIR / "credit_debug.png"
                shot.parent.mkdir(exist_ok=True)
                await page.screenshot(path=str(shot), full_page=False)
                log_cb(f"  Screenshot disimpan: {shot.absolute()}")
            except Exception:
                pass

        if result_cb:
            result_cb(credits)

        if auto_close:
            log_cb("  Browser ditutup otomatis.")
        else:
            log_cb("  Browser terbuka — tutup manual setelah selesai.")
            try:
                await page.wait_for_event("close", timeout=120000)
            except Exception:
                pass


async def _scan_page_for_credits(page, log_cb) -> str:
    """Scan body text halaman untuk cari teks kredit yang terlihat di UI."""
    try:
        body_text = await page.inner_text("body")
    except Exception:
        return ""
    patterns = [
        r'(\d[\d,]*)\s*credits?\s*(?:left|remaining|available)?',
        r'credits?\s*[:\-]?\s*(\d[\d,]*)',
        r'(\d[\d,]*)\s*/\s*\d[\d,]*\s*credits?',
        r'(\d[\d,]*)\s*/?s*credits?',
        r'remaining\s*[:\-]?\s*(\d[\d,]*)',
        r'balance\s*[:\-]?\s*(\d[\d,]*)',
    ]
    for pat in patterns:
        m = re.search(pat, body_text, re.IGNORECASE)
        if m:
            result = m.group(0).strip()
            log_cb(f"    Ditemukan: '{result}'")
            return result
    return ""


async def _check_credits_in_context(context, log_cb):
    """Buka new page khusus agar tidak mengganggu page generate yang sedang aktif."""
    import asyncio

    # Selalu pakai new page terpisah supaya tidak konflik dengan halaman generate
    cred_page = None
    try:
        cred_page = await context.new_page()
    except Exception as e:
        log_cb(f"  [KREDIT] Gagal buat halaman baru: {e}")
        return None

    credits = None
    for url in ["https://suno.com/create", "https://suno.com/account", "https://suno.com"]:
        try:
            log_cb(f"  [KREDIT] Buka {url} ...")
            await cred_page.goto(url, wait_until="commit", timeout=30000)
            await asyncio.sleep(2)
            if "about:blank" in cred_page.url or "chrome-error" in cred_page.url:
                log_cb("  [KREDIT] Halaman blank, coba URL berikutnya...")
                continue
            try:
                await cred_page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            try:
                await cred_page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass
            for _wc in range(12):  # polling max 12s
                await asyncio.sleep(1)
                _bc = ""
                try:
                    _bc = await cred_page.inner_text("body")
                except Exception:
                    pass
                if any(kw in _bc.lower() for kw in ["credits", "credit", "remaining", "balance"]):
                    break
            credits = await _scan_page_for_credits(cred_page, log_cb)
            if credits:
                break
        except Exception as e:
            log_cb(f"  [KREDIT] warning: {e}")

    # Tutup halaman kredit agar tidak menumpuk
    try:
        await cred_page.close()
    except Exception:
        pass

    return parse_credit_value(credits)


# ------------------------------------------------------------------
# Download helpers
# ------------------------------------------------------------------

async def _download_generated_songs(context, page, titles, count, log_cb, description: str = ""):
    import asyncio, urllib.request

    # Buat subfolder berdasarkan style/prompt
    _folder_name = _prompt_to_folder_name(description) if description else "suno_songs"
    out_dir = SONGS_DIR / _folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log_cb(f"  [DL] Folder: .../{_folder_name}/")

    try:
        await page.goto("https://suno.com/me", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
    except Exception as e:
        log_cb(f"  warning reload: {e}")

    max_songs = count * 2
    song_entries = []
    try:
        for a in await page.query_selector_all("a[href*='/song/']"):
            href = await a.get_attribute("href") or ""
            if href.startswith("/"):
                href = "https://suno.com" + href
            if "/song/" in href and not any(e[0] == href for e in song_entries):
                suno_title = ""
                try:
                    for title_sel in ["[class*='title']", "[class*='name']", "h2", "h3", "p"]:
                        try:
                            parent = await a.evaluate_handle(
                                "el => el.closest('[class*=\"card\"], [class*=\"item\"], article, li') || el.parentElement"
                            )
                            t_el = await parent.query_selector(title_sel)
                            if t_el:
                                t = (await t_el.inner_text() or "").strip()
                                if t and len(t) > 1:
                                    suno_title = t
                                    break
                        except Exception:
                            continue
                    if not suno_title:
                        suno_title = (await a.inner_text() or "").strip()
                except Exception:
                    pass
                song_entries.append((href, suno_title))
            if len(song_entries) >= max_songs:
                break
        log_cb(f"  Ditemukan {len(song_entries)} song link")
    except Exception as e:
        log_cb(f"  Error scan link: {e}")

    downloaded = 0
    for i, (song_url, suno_title) in enumerate(song_entries[:max_songs]):
        if is_stop_requested():
            break
        version = "a" if i % 2 == 0 else "b"
        title_idx = i // 2
        if suno_title:
            base_name = make_safe_filename(suno_title)
        elif title_idx < len(titles):
            base_name = make_safe_filename(titles[title_idx])
        else:
            base_name = f"suno_{i+1}"

        save_path = out_dir / f"{base_name}_{version}.mp3"
        c = 1
        while save_path.exists():
            save_path = out_dir / f"{base_name}_{version}_{c}.mp3"
            c += 1

        log_cb(f"\n  [DL] {i+1}/{len(song_entries)}: '{base_name}_{version}.mp3'")
        if await _download_single_song(context, song_url, save_path, log_cb, fetch_title=False):
            downloaded += 1

    if downloaded == 0:
        log_cb("\n  [DL] Fallback CDN scan...")
        try:
            html = await page.content()
            mp3_urls = list(dict.fromkeys(re.findall(r'https://cdn\d*\.suno\.ai/[a-f0-9\-]+\.mp3', html)))
            log_cb(f"    Found {len(mp3_urls)} CDN URL(s)")
            for j, url in enumerate(mp3_urls[:max_songs]):
                if is_stop_requested():
                    break
                title_idx = j // 2
                version = "a" if j % 2 == 0 else "b"
                base_name = make_safe_filename(titles[title_idx]) if title_idx < len(titles) else f"suno_{j+1}"
                save_path = out_dir / f"{base_name}_{version}.mp3"
                try:
                    req = urllib.request.Request(url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                        "Referer": "https://suno.com/"
                    })
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        data = resp.read()
                    save_path.write_bytes(data)
                    log_cb(f"    \u2713 {save_path.name} ({len(data)//1024} KB)")
                    downloaded += 1
                except Exception as e:
                    log_cb(f"    CDN error: {e}")
        except Exception as e:
            log_cb(f"    CDN scan error: {e}")

    if downloaded > 0:
        log_cb(f"\n[DL] \u2713 {downloaded} file disimpan di '{out_dir.absolute()}'")
    else:
        log_cb("[DL] Download otomatis gagal \u2014 download manual dari Library Suno.")


async def _dismiss_commercial_popup(page, log_cb=None):
    """
    FIX: Fungsi ini sebelumnya dipanggil di _download_single_song tapi tidak
    pernah didefinisikan → NameError force close saat download dimulai.
    Dismiss popup 'Got it' / 'commercial rights' sebelum klik menu download.
    Timeout 800ms agar tidak memperlambat jika popup tidak ada.
    """
    import asyncio
    for sel in [
        "button:has-text('Got it')",
        "button:has-text('Maybe later')",
        "button:has-text('Not now')",
        "button[aria-label='Close']",
        "button[aria-label*='close' i]",
        "button[aria-label*='dismiss' i]",
    ]:
        try:
            el = await page.wait_for_selector(sel, timeout=800, state="visible")
            if el:
                await el.click()
                if log_cb:
                    log_cb(f"    [POPUP] Closed: {sel}")
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


async def _download_single_song(context, song_url: str, save_path: Path, log_cb,
                                 fetch_title: bool = False) -> bool:
    """
    Download satu lagu dari halaman suno.com/song/[id].
    fetch_title=False → nama file dari save_path (judul DeepSeek), tidak override dari Suno.

    Alur:
      1. Buka halaman lagu
      2. Ambil judul asli (rename file)
      3. Dismiss popup komersial
      4. Klik tombol menu (⋯ / More)
      5. Klik "Download" di dropdown
      6. Klik "MP3 Audio" di sub-menu
      7. Tunggu popup konfirmasi "Download Anyway" → langsung klik
      8. Simpan file, cek ukuran (skip jika preview/clip)
      Retry internal tidak ada — retry dikelola di caller.
    """
    import asyncio
    sp = await context.new_page()
    got = False
    try:
        await sp.goto(song_url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(1)  # FIX: cukup 1s

        # -- Skip lagu versi Preview (badge "v5.5 Preview" + gembok) --
        # Lagu NORMAL: badge "v4.5-all", "v4.5", "v3.5" — TIDAK ada kata "Preview"
        # Lagu PREVIEW: badge "v5.5 Preview" — ada kata " Preview" di badge versi
        # Cara deteksi: cek seluruh teks badge/label kecil di halaman lagu
        _is_preview_song = False
        try:
            # Ambil semua badge/label kecil versi yang biasa ada di bawah tanggal
            _badge_sels = [
                "a[class*='version' i]",
                "span[class*='version' i]",
                "div[class*='version' i]",
                "[class*='model' i]",
                "[class*='tag' i]",
                "[class*='badge' i]",
            ]
            for _bsel in _badge_sels:
                _bels = await sp.query_selector_all(_bsel)
                for _bel in _bels:
                    try:
                        _btxt = (await _bel.inner_text()).strip()
                        # Badge preview: teksnya mengandung " Preview" (case-insensitive)
                        # Badge normal: "v4.5-all", "v4.5", "v3.5" dll
                        if _btxt.lower().endswith(" preview") or " preview" in _btxt.lower():
                            _is_preview_song = True
                            log_cb(f"    [SKIP] Badge versi Preview terdeteksi: '{_btxt}' - dilewati: {save_path.name}")
                            break
                    except Exception:
                        pass
                if _is_preview_song:
                    break
        except Exception:
            pass

        # Fallback: cek via page title atau meta jika badge tidak ditemukan
        if not _is_preview_song:
            try:
                _page_text = await sp.inner_text("body")
                # Cari pola versi di body: "v5.5 Preview" tapi BUKAN "v4.5-all" atau "v4.5"
                import re as _re
                _ver_matches = _re.findall(r'v[\d.]+\s+Preview', _page_text, _re.IGNORECASE)
                if _ver_matches:
                    _is_preview_song = True
                    log_cb(f"    [SKIP] Versi Preview terdeteksi via body: {_ver_matches[0]} - dilewati: {save_path.name}")
            except Exception:
                pass

        if _is_preview_song:
            # Buat marker file agar caller tahu ini preview-skip, bukan error biasa
            try:
                marker = save_path.parent / (save_path.stem + "__preview_skip.mp3")
                marker.touch()
            except Exception:
                pass
            return False

        # ── Ambil judul asli ──────────────────────────────────────────
        if fetch_title:
            actual_title = await _get_song_title_from_page(sp)
            if actual_title:
                out_dir      = save_path.parent
                ver_suffix   = save_path.stem.rsplit("_", 1)[-1]
                if ver_suffix not in ("a", "b"):
                    ver_suffix = ""
                safe_title = make_safe_filename(actual_title)
                new_name   = (f"{safe_title}_{ver_suffix}.mp3"
                              if ver_suffix else f"{safe_title}.mp3")
                new_path   = out_dir / new_name
                counter    = 1
                while new_path.exists():
                    stem     = (f"{safe_title}_{ver_suffix}_{counter}"
                                if ver_suffix else f"{safe_title}_{counter}")
                    new_path = out_dir / f"{stem}.mp3"
                    counter += 1
                save_path = new_path
                log_cb(f"    Judul: '{actual_title}' -> {save_path.name}")

        # FIX: Skip dismiss popup — langsung ke menu titik 3
        # ── Klik tombol menu (More / ⋯) ──────────────────────────────
        menu_selectors = [
            "button[aria-label*='more' i]",
            "button[aria-label*='option' i]",
            "button[aria-label*='menu' i]",
            "button[aria-haspopup='menu']",
            "[data-testid*='more' i]",
            "[data-testid*='option' i]",
        ]
        menu_ok = False
        for msel in menu_selectors:
            try:
                b = await sp.wait_for_selector(msel, timeout=3000, state="visible")
                if b:
                    await b.click()
                    menu_ok = True
                    await asyncio.sleep(0.8)
                    log_cb(f"    [DL] Menu terbuka via: {msel}")
                    break
            except Exception:
                continue

        if not menu_ok:
            log_cb(f"    [DL] ✗ Menu tidak ditemukan: {save_path.name}")
            return False

        # ── Klik "Download" di dropdown ───────────────────────────────
        dl_item_found = False
        for dsel in [
            "[role='menuitem']:has-text('Download')",
            "li:has-text('Download')",
            "button:has-text('Download')",
            "text=Download",
        ]:
            try:
                d = await sp.wait_for_selector(dsel, timeout=3000, state="visible")
                if d:
                    await d.click()
                    dl_item_found = True
                    await asyncio.sleep(0.8)
                    log_cb(f"    [DL] Klik 'Download'")
                    break
            except Exception:
                continue

        if not dl_item_found:
            log_cb(f"    [DL] ✗ Item Download tidak ditemukan di menu")
            return False

        # ── Klik "MP3 Audio" di sub-menu ─────────────────────────────
        mp3_found = False
        for m2sel in [
            "[role='menuitem']:has-text('MP3 Audio')",
            "li:has-text('MP3 Audio')",
            "button:has-text('MP3 Audio')",
            "text=MP3 Audio",
            "text=MP3",
        ]:
            try:
                m2 = await sp.wait_for_selector(m2sel, timeout=3000, state="visible")
                if m2:
                    await m2.click()
                    mp3_found = True
                    await asyncio.sleep(0.5)
                    log_cb(f"    [DL] Klik 'MP3 Audio'")
                    break
            except Exception:
                continue

        if not mp3_found:
            log_cb(f"    [DL] ✗ MP3 Audio tidak ditemukan di sub-menu")
            return False

        # ── Tunggu popup "Download Anyway" → langsung klik ───────────
        # Popup ini muncul setelah klik MP3 Audio (konfirmasi Suno)
        try:
            anyway_btn = await sp.wait_for_selector(
                "button:has-text('Download Anyway')",
                timeout=8000,
                state="visible"
            )
            if anyway_btn:
                log_cb(f"    [DL] Popup 'Download Anyway' muncul → klik!")
                async with sp.expect_download(timeout=60000) as dl_info:
                    await anyway_btn.click()
                dl_result = await dl_info.value
                await dl_result.save_as(str(save_path))
                _kb = save_path.stat().st_size // 1024
                min_kb = load_app_config().get("min_song_kb", MIN_FULL_SONG_KB)
                if _kb < min_kb:
                    log_cb(f"    [DL] ⚠ SKIP preview/clip: {save_path.name} ({_kb} KB < {min_kb} KB)")
                    try: save_path.unlink()
                    except Exception: pass
                    got = False
                else:
                    log_cb(f"    [DL] ✓ {save_path.name} ({_kb} KB)")
                    got = True
        except Exception as e_aw:
            log_cb(f"    [DL] Popup Download Anyway tidak muncul ({e_aw.__class__.__name__}) — retry menu...")
            try:
                await asyncio.sleep(0.5)
                for _rm in ["button[aria-label*='more' i]","button[aria-haspopup='menu']","[data-testid*='more' i]"]:
                    try:
                        _rb = await sp.wait_for_selector(_rm, timeout=2000, state="visible")
                        if _rb: await _rb.click(); await asyncio.sleep(0.6); break
                    except Exception: continue
                for _rd in ["[role='menuitem']:has-text('Download')","text=Download"]:
                    try:
                        _rdd = await sp.wait_for_selector(_rd, timeout=2000, state="visible")
                        if _rdd: await _rdd.click(); await asyncio.sleep(0.6); break
                    except Exception: continue
                for _rm2 in ["[role='menuitem']:has-text('MP3 Audio')","text=MP3 Audio","text=MP3"]:
                    try:
                        _rm2el = await sp.wait_for_selector(_rm2, timeout=2000, state="visible")
                        if _rm2el:
                            async with sp.expect_download(timeout=30000) as _rdi:
                                await _rm2el.click()
                                try:
                                    _raw = await sp.wait_for_selector(
                                        "button:has-text('Download Anyway')",
                                        timeout=6000, state="visible")
                                    if _raw: await _raw.click()
                                except Exception: pass
                            _rdl = await _rdi.value
                            await _rdl.save_as(str(save_path))
                            _kb2 = save_path.stat().st_size // 1024
                            _min2 = load_app_config().get("min_song_kb", MIN_FULL_SONG_KB)
                            if _kb2 >= _min2:
                                log_cb(f"    [DL] ✓ {save_path.name} ({_kb2} KB) via retry")
                                got = True
                            else:
                                log_cb(f"    [DL] ⚠ SKIP clip retry: {_kb2} KB")
                                try: save_path.unlink()
                                except Exception: pass
                            break
                    except Exception: continue
            except Exception as _re: log_cb(f"    [DL] ✗ Retry gagal: {_re}")
            if got: return got
            log_cb(f"    [DL] Coba download langsung (akun premium / no-popup)...")
            try:
                async with sp.expect_download(timeout=10000) as dl_info2:
                    pass
                dl_result2 = await dl_info2.value
                await dl_result2.save_as(str(save_path))
                _kb2 = save_path.stat().st_size // 1024
                min_kb2 = load_app_config().get("min_song_kb", MIN_FULL_SONG_KB)
                if _kb2 < min_kb2:
                    log_cb(f"    [DL] ⚠ SKIP preview: {save_path.name} ({_kb2} KB)")
                    try: save_path.unlink()
                    except Exception: pass
                else:
                    log_cb(f"    [DL] ✓ {save_path.name} ({_kb2} KB) [no-popup]")
                    got = True
            except Exception:
                log_cb(f"    [DL] ✗ Gagal download {save_path.name}")

    except Exception as e_outer:
        log_cb(f"    [DL] ✗ Error luar: {e_outer}")
    finally:
        try: await sp.close()
        except Exception: pass
    return got

# ------------------------------------------------------------------
# Download helpers: pakai context yang sudah ada
# ------------------------------------------------------------------

async def _download_top_n_in_context(context, count: int, log_cb, description: str = "", ai_titles: list = None):
    """
    Download lagu berdasarkan title-matching ketat terhadap AI titles.
    JAMINAN:
    - Hanya lagu yang judulnya COCOK (fuzzy ≥55%) dengan title_a/title_b yang didownload
    - Lagu LAMA di library TIDAK ikut ter-download (tidak masuk antrian)
    - Setiap download di-log: judul AI, DOM title, folder tujuan
    - Lagu tidak cocok → di-SKIP (dicatat, bukan dianggap error)
    """
    import asyncio, re as _re

    MAX_RETRY = 2
    FUZZY_THR = 0.55  # minimal 55% kata cocok

    def _norm(s):
        return _re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    def _fuzzy_ok(ai_t: str, dom_t: str) -> bool:
        na = _norm(ai_t); nd = _norm(dom_t)
        if not na: return False
        if na in nd or nd in na: return True
        wa = set(na.split()); wd = set(nd.split())
        return bool(wa) and len(wa & wd) / len(wa) >= FUZZY_THR

    # ─── 1. Scan library suno.com/me ────────────────────────────────────────
    log_cb(f"[DL] Scan library suno.com/me untuk mencocokkan judul AI...")
    page = await context.new_page()
    try:
        await page.goto("https://suno.com/me", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        all_songs = []; prev = -1; scroll = 0; max_s = max(8, count + 6)
        while scroll < max_s:
            raw = await page.evaluate("""
                () => {
                    const r = [], seen = new Set();
                    document.querySelectorAll("a[href*='/song/']").forEach(a => {
                        let h = a.href || a.getAttribute('href') || '';
                        if (!h.startsWith('http')) h = 'https://suno.com' + h;
                        if (!h.includes('/song/') || seen.has(h)) return;
                        seen.add(h);
                        let el = a, isPv = false;
                        for (let i = 0; i < 10; i++) {
                            if (!el) break;
                            for (const b of (el.querySelectorAll ? el.querySelectorAll('*') : [])) {
                                if (b.children.length === 0 &&
                                    /\bpreview\b/i.test((b.textContent||'').trim()) &&
                                    b.textContent.trim().length < 30) { isPv = true; break; }
                            }
                            if (isPv) break; el = el.parentElement;
                        }
                        let el2 = a, dt = '';
                        for (let i = 0; i < 8; i++) {
                            if (!el2) break;
                            for (const t of (el2.querySelectorAll
                                ? el2.querySelectorAll('[class*="title" i],[class*="name" i],p,h3,h4')
                                : [])) {
                                const tx = (t.textContent || '').trim();
                                if (tx.length > 1 && tx.length < 120) { dt = tx; break; }
                            }
                            if (dt) break; el2 = el2.parentElement;
                        }
                        r.push({ href: h, domTitle: dt, isPreview: isPv });
                    });
                    return r;
                }
            """)
            for item in raw:
                url = item.get("href", ""); dt = item.get("domTitle", "").strip()
                if not url or "/song/" not in url: continue
                if any(s["url"] == url for s in all_songs): continue
                all_songs.append({"url": url, "dom_title": dt, "is_preview": item.get("isPreview", False)})
            if len(all_songs) == prev: break
            prev = len(all_songs)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2.5); scroll += 1
            log_cb(f"  Scroll {scroll}/{max_s} — {len(all_songs)} lagu terdeteksi di library")
            if len(all_songs) >= count + 14: break

        non_pv = [s for s in all_songs if not s["is_preview"]]
        log_cb(f"  Library scan selesai: {len(non_pv)} normal | {len(all_songs)-len(non_pv)} preview (dilewati)")

        _fn     = _prompt_to_folder_name(description) if description else "suno_songs"
        out_dir = SONGS_DIR / _fn

        # ─── 2. Bangun antrian download ──────────────────────────────────────
        if not ai_titles:
            log_cb(f"  [DL] Tidak ada ai_titles → fallback N-teratas ({count} lagu)")
            dl_queue = []
            for idx, s in enumerate(list(reversed(non_pv[:count])), 1):
                pair   = ((idx - 1) % 2) + 1
                folder = out_dir.parent / (out_dir.name + f"_{pair}")
                folder.mkdir(parents=True, exist_ok=True)
                dl_queue.append({
                    "url": s["url"], "filename": f"suno_dl_{idx}",
                    "folder": folder, "song_idx": idx, "pair": pair,
                    "dom_title": s["dom_title"], "title_src": "fallback (N-teratas)",
                    "fetch_title": True
                })
        else:
            used_urls = set(); dl_queue = []; not_found = []

            for song_idx, sd in enumerate(ai_titles, 1):
                ta = (sd.get("title_a") or sd.get("title") or "").strip()
                tb = (sd.get("title_b") or ta).strip()

                match_a = match_b = None
                for s in non_pv:
                    if s["url"] in used_urls: continue
                    dt = s["dom_title"]
                    if not match_a and _fuzzy_ok(ta, dt):
                        match_a = s; used_urls.add(s["url"])
                    elif not match_b and tb != ta and _fuzzy_ok(tb, dt):
                        match_b = s; used_urls.add(s["url"])
                    if match_a and match_b: break

                # FIX: Suno selalu generate 2 variasi dengan JUDUL SAMA di DOM.
                # Jika title_b (AI-alt) tidak cocok → cari URL ke-2 yang judulnya = title_a
                # Ini handle kasus Suno pakai 1 judul untuk kedua versi (paling umum)
                if match_a and not match_b:
                    for s in non_pv:
                        if s["url"] not in used_urls and _fuzzy_ok(ta, s["dom_title"]):
                            match_b = s; used_urls.add(s["url"])
                            log_cb(f"  [MATCH ✓] Lagu {song_idx} versi B (fallback judul sama)  →  DOM: '{s['dom_title'][:50]}'")
                            break

                def _make_item(match, pair_n, title_used, tsrc, _si=song_idx):
                    folder = out_dir.parent / (out_dir.name + f"_{pair_n}")
                    folder.mkdir(parents=True, exist_ok=True)
                    return {
                        "url": match["url"], "filename": make_safe_filename(title_used),
                        "folder": folder, "song_idx": _si, "pair": pair_n,
                        "title_src": tsrc, "dom_title": match["dom_title"], "fetch_title": False
                    }

                if match_a:
                    dl_queue.append(_make_item(match_a, 1, ta, f"AI title_a '{ta}'"))
                    log_cb(f"  [MATCH ✓] Lagu {song_idx} versi A  →  DOM: '{match_a['dom_title'][:50]}'")
                else:
                    log_cb(f"  [SKIP  ✗] Lagu {song_idx} versi A '{ta}' — tidak cocok (belum render / judul beda)")
                    not_found.append(f"Lagu {song_idx} versi A — '{ta}'")

                if match_b:
                    # FIX: versi B SELALU pakai title_b (AI alt title) sebagai nama file
                    # Meski DOM title-nya sama dengan versi A (Suno pakai judul sama),
                    # nama file harus berbeda sesuai judul AI yang di-generate
                    _b_fname = tb  # SELALU title_b, bukan title_a
                    _b_src   = f"AI title_b '{tb}'" if _fuzzy_ok(tb, match_b["dom_title"]) else f"AI title_b '{tb}' (fallback-url)"
                    dl_queue.append(_make_item(match_b, 2, _b_fname, f"{_b_src} (folder_2)"))
                    log_cb(f"  [MATCH ✓] Lagu {song_idx} versi B  →  nama: '{_b_fname}'  DOM: '{match_b['dom_title'][:50]}'")
                else:
                    log_cb(f"  [SKIP  ✗] Lagu {song_idx} versi B — hanya 1 versi tersedia di library")
                    not_found.append(f"Lagu {song_idx} versi B (hanya 1 versi di library)")

            if not_found:
                log_cb(f"\n  ⚠ {len(not_found)} item di-SKIP:")
                for nf in not_found:
                    log_cb(f"     ✗ {nf}")
                log_cb("  Catatan: versi B di-skip = hanya 1 versi render di library saat itu.")
                log_cb("  → Lagu LAMA di library TIDAK ikut ter-download.\n")

        # ─── 3. Eksekusi download ─────────────────────────────────────────────
        downloaded = 0; retry_q = []
        for item in dl_queue:
            if is_stop_requested():
                log_cb("  [STOP] Download dihentikan oleh user."); break

            url    = item["url"]; fn   = item["filename"]
            folder = item["folder"]; si  = item["song_idx"]
            pair   = item["pair"];   tsrc = item.get("title_src", "")
            ver    = "versi utama" if pair == 1 else "versi alt"

            log_cb(f"\n  [DL] Lagu {si} {ver}")
            log_cb(f"       Nama file: {fn}.mp3")
            log_cb(f"       Src      : {tsrc}")
            log_cb(f"       DOM title: {item.get('dom_title', '')[:60]}")
            log_cb(f"       Folder   : .../{folder.parent.name}/{folder.name}/")

            sp = folder / f"{fn}.mp3"; c = 1
            while sp.exists(): sp = folder / f"{fn}_{c}.mp3"; c += 1

            ok = await _download_single_song(context, url, sp, log_cb, fetch_title=item["fetch_title"])
            if ok:
                downloaded += 1
                log_cb(f"       ✓ Tersimpan: {sp.name}")
            else:
                pm = folder / (fn + "__preview_skip.mp3")
                if pm.exists():
                    try: pm.unlink()
                    except: pass
                    log_cb(f"       ✗ Dilewati (hanya preview)")
                else:
                    retry_q.append(item)
                    log_cb(f"       ✗ Gagal — masuk antrian retry")

        # ─── 4. Retry ─────────────────────────────────────────────────────────
        if retry_q and not is_stop_requested():
            log_cb(f"\n[DL] Retry {len(retry_q)} lagu gagal...")
            for att in range(1, MAX_RETRY + 1):
                if not retry_q or is_stop_requested(): break
                still_fail = []; await asyncio.sleep(4)
                for item in retry_q:
                    if is_stop_requested(): break
                    _sp = item["folder"] / f"{item['filename']}_r{att}.mp3"; c2 = 1
                    while _sp.exists(): _sp = item["folder"] / f"{item['filename']}_r{att}_{c2}.mp3"; c2 += 1
                    log_cb(f"  [RETRY {att}] {item['filename']}  ({item.get('title_src', '')})")
                    ok = await _download_single_song(context, item["url"], _sp, log_cb, fetch_title=False)
                    if ok:
                        downloaded += 1; log_cb(f"  [RETRY {att}] ✓")
                    else:
                        still_fail.append(item)
                retry_q = still_fail

        log_cb(f"\n[DL] ✅ {downloaded}/{len(dl_queue)} lagu berhasil → '{out_dir.absolute()}'")
        if ai_titles:
            log_cb("     Catatan: hanya lagu judul cocok yang didownload. Lagu lama diabaikan.")
    finally:
        try: await page.close()
        except: pass

# ------------------------------------------------------------------
# Download latest (standalone)
# ------------------------------------------------------------------

def run_download_latest_two(chrome_path: str, profile_dir: str, log_cb):
    import asyncio
    try:
        _run_async(_async_download_latest(chrome_path, profile_dir, log_cb))
    except Exception as e:
        log_cb(f"ERROR: {e}")


def run_download_latest_n(chrome_path: str, profile_dir: str, count: int, log_cb):
    profile_dir = resolve_profile_dir(profile_dir)  # FIX portable path
    import asyncio
    try:
        _run_async(_async_download_n_latest(chrome_path, profile_dir, count, log_cb))
    except Exception as e:
        log_cb(f"ERROR: {e}")


async def _async_download_latest(chrome_path: str, profile_dir: str, log_cb):
    """Wrapper untuk download 2 lagu terbaru (tombol Download 2 Lagu Teratas)."""
    await _async_download_n_latest(chrome_path, profile_dir, 2, log_cb)


async def _async_download_n_latest(chrome_path: str, profile_dir: str, count: int, log_cb, description: str = ""):
    """Download N lagu terbaru dari library Suno. Sama persis dengan tombol Download."""
    import asyncio

    async with (await _launch_context(chrome_path, profile_dir, log_cb)) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        log_cb(f"[DL] Buka library Suno (ambil {count} lagu teratas)...")
        await page.goto("https://suno.com/me", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        song_urls = []
        try:
            for a in await page.query_selector_all("a[href*='/song/']"):
                href = await a.get_attribute("href") or ""
                if href.startswith("/"):
                    href = "https://suno.com" + href
                if "/song/" in href and href not in song_urls:
                    song_urls.append(href)
                if len(song_urls) >= count:
                    break
        except Exception as e:
            log_cb(f"  Error: {e}")

        log_cb(f"[DL] {len(song_urls)} lagu ditemukan")
        _folder_name = _prompt_to_folder_name(description) if description else "suno_songs"
        out_dir = SONGS_DIR / _folder_name
        out_dir.mkdir(parents=True, exist_ok=True)
        log_cb(f"  [DL] Folder: .../{_folder_name}/")

        MAX_RETRY = 2
        failed_urls = []
        downloaded = 0

        for idx, url in enumerate(song_urls[:count], 1):
            placeholder = out_dir / f"suno_latest_{idx}.mp3"
            log_cb(f"[DL] Lagu {idx}/{count}...")
            ok = await _download_single_song(context, url, placeholder, log_cb, fetch_title=False)
            if ok:
                downloaded += 1
            else:
                failed_urls.append((idx, url))
                log_cb(f"  Lagu {idx} gagal, ditandai untuk retry.")

        # Retry
        if failed_urls:
            log_cb(f"\n[DL] Retry {len(failed_urls)} lagu yang gagal...")
            import asyncio
            for attempt in range(1, MAX_RETRY + 1):
                if not failed_urls:
                    break
                still_failed = []
                await asyncio.sleep(3)
                for idx, url in failed_urls:
                    log_cb(f"  [RETRY {attempt}] Lagu {idx}...")
                    placeholder = out_dir / f"suno_latest_{idx}_retry{attempt}.mp3"
                    ok = await _download_single_song(context, url, placeholder, log_cb, fetch_title=False)
                    if ok:
                        downloaded += 1
                        log_cb(f"  [RETRY {attempt}] Lagu {idx} berhasil!")
                    else:
                        still_failed.append((idx, url))
                failed_urls = still_failed

            if failed_urls:
                log_cb(f"  {len(failed_urls)} lagu tetap gagal setelah {MAX_RETRY}x retry.")

        log_cb(f"[DL] Selesai. {downloaded}/{count} file di '{out_dir.absolute()}'")
        return downloaded



def parse_credit_value(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    nums = re.findall(r'\d[\d,]*', s)
    if not nums:
        return None
    try:
        return int(nums[0].replace(",", ""))
    except Exception:
        return None


def get_profile_credit_quota(prof: dict) -> int:
    value = parse_credit_value(prof.get("credits_remaining"))
    if prof.get("is_premium", False):
        return MAX_CREATES
    if value is None:
        return 0
    return max(0, min(MAX_CREATES, value // FREE_CREDITS_PER_CREATE))

def get_profile_max_from_credits(prof: dict) -> int:
    """Hitung max lagu dari kredit real TANPA batasan MAX_CREATES (untuk mode Habiskan Semua)."""
    if prof.get("is_premium", False):
        return MAX_CREATES
    value = parse_credit_value(prof.get("credits_remaining"))
    if value is None or value <= 0:
        return 0
    return max(0, value // FREE_CREDITS_PER_CREATE)


def deduct_profile_credit(prof: dict, amount: int = 1):
    if prof.get("is_premium", False):
        return
    cur = parse_credit_value(prof.get("credits_remaining"))
    if cur is None:
        cur = 0
    prof["credits_remaining"] = max(0, cur - (amount * FREE_CREDITS_PER_CREATE))



# ------------------------------------------------------------------
# RuntimeSettings Dialog
# ------------------------------------------------------------------

class RuntimeSettingsDialog(tk.Toplevel):
    """Dialog pengaturan runtime: headless, background window, captcha pause, jeda, min KB."""

    WINDOW_MODES = [
        ("Normal (Chrome muncul di depan)",              "normal"),
        ("Background (Chrome muncul tapi di belakang)",  "background"),
        ("Headless (Chrome invisible, tidak ada window)", "headless"),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Runtime Settings")
        self.geometry("520x680")
        self.minsize(520, 500)
        self.resizable(True, True)
        self.grab_set()

        cfg = load_app_config()

        # ── Tombol Save/Batal di-pack PERTAMA → selalu terlihat di bawah ──
        bf = ttk.Frame(self, padding=(8, 6))
        bf.pack(side="bottom", fill="x")
        ttk.Button(bf, text="💾 Simpan", command=self._save, width=14).pack(side="left", padx=6)
        ttk.Button(bf, text="Batal",     command=self.destroy, width=10).pack(side="left", padx=6)
        ttk.Separator(self).pack(side="bottom", fill="x")

        # ── Canvas scrollable untuk konten form ──
        _canvas = tk.Canvas(self, highlightthickness=0)
        _vsb    = ttk.Scrollbar(self, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        frm = ttk.Frame(_canvas, padding=16)
        frm.columnconfigure(1, weight=1)
        _cwin = _canvas.create_window((0, 0), window=frm, anchor="nw")

        def _on_resize(e):
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        def _on_canvas_resize(e):
            _canvas.itemconfig(_cwin, width=e.width)
        frm.bind("<Configure>", _on_resize)
        _canvas.bind("<Configure>", _on_canvas_resize)

        def _on_wheel(e):
            _canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        _canvas.bind_all("<MouseWheel>", _on_wheel)

        frm.columnconfigure(1, weight=1)

        # --- Mode Window Chrome ---
        ttk.Label(frm, text="Mode Window Chrome:", font=("", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(4, 6))

        current_mode = cfg.get("window_mode", "normal")
        self.window_mode_var = tk.StringVar(value=current_mode)
        for i, (label, val) in enumerate(self.WINDOW_MODES):
            ttk.Radiobutton(frm, text=label, variable=self.window_mode_var, value=val,
                            ).grid(row=1+i, column=0, columnspan=2, sticky="w", padx=16, pady=2)

        ttk.Label(frm,
            text="• Normal: Chrome muncul di layar (default)\n"
                 "• Background: Chrome berjalan tapi tidak mengganggu (otomatis minimize/always-below)\n"
                 "• Headless: Chrome invisible total — hanya jika sudah login sebelumnya",
            foreground="gray", font=("", 8), justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 8))

        ttk.Separator(frm).grid(row=5, column=0, columnspan=2, sticky="ew", pady=6)

        # --- Captcha Handler ---
        ttk.Label(frm, text="Jika CAPTCHA terdeteksi:", font=("", 9, "bold")).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(4, 4))

        self.captcha_action_var = tk.StringVar(value=cfg.get("captcha_action", "pause"))
        for val, label in [
            ("pause", "⏸ Pause & tampilkan notifikasi — tunggu user selesaikan captcha"),
            ("skip",  "⏭ Skip profile ini dan lanjut ke profile berikutnya"),
        ]:
            ttk.Radiobutton(frm, text=label, variable=self.captcha_action_var, value=val,
                            ).grid(row=7 if val=="pause" else 8, column=0, columnspan=2,
                                   sticky="w", padx=16, pady=2)

        self.captcha_timeout_var = tk.IntVar(value=cfg.get("captcha_timeout_sec", 120))
        tf = ttk.Frame(frm)
        tf.grid(row=9, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 8))
        ttk.Label(tf, text="Timeout tunggu captcha (detik):").pack(side="left")
        ttk.Spinbox(tf, from_=30, to=600, increment=30,
                    textvariable=self.captcha_timeout_var, width=7).pack(side="left", padx=(8,0))

        ttk.Separator(frm).grid(row=10, column=0, columnspan=2, sticky="ew", pady=6)

        # --- Resolusi Window Chrome ---
        _WIN_SIZES = ["1280x720", "1366x768", "1440x900", "1920x1080"]
        ttk.Label(frm, text="Resolusi window Chrome:").grid(row=11, column=0, sticky="w", pady=5)
        self.window_size_var = tk.StringVar(value=cfg.get("window_size", "1366x768"))
        ttk.Combobox(frm, textvariable=self.window_size_var,
                     values=_WIN_SIZES, state="readonly", width=14
                     ).grid(row=11, column=1, sticky="w", pady=5)
        ttk.Label(frm, text="  ↳ Override fingerprint, berlaku semua profil",
                  foreground="gray").grid(row=12, column=0, columnspan=2, sticky="w", padx=4, pady=(0,4))

        ttk.Separator(frm).grid(row=13, column=0, columnspan=2, sticky="ew", pady=6)

        # --- Jeda & ukuran file ---
        ttk.Label(frm, text="Jeda antar lagu — Min (detik):").grid(row=14, column=0, sticky="w", pady=5)
        self.wait_min_var = tk.IntVar(value=cfg.get("wait_between_min", 50))
        ttk.Spinbox(frm, from_=10, to=600, increment=5,
                    textvariable=self.wait_min_var, width=8,
                    ).grid(row=14, column=1, sticky="w", padx=(8, 0), pady=5)

        ttk.Label(frm, text="Jeda antar lagu — Maks (detik):").grid(row=15, column=0, sticky="w", pady=5)
        self.wait_max_var = tk.IntVar(value=cfg.get("wait_between_max", 100))
        ttk.Spinbox(frm, from_=10, to=600, increment=5,
                    textvariable=self.wait_max_var, width=8,
                    ).grid(row=15, column=1, sticky="w", padx=(8, 0), pady=5)
        # FIX#4c: label info di row sendiri (row=13), tidak tumpang tindih dengan Spinbox Maks
        ttk.Label(frm, text="  ↳ Jeda akan random antara Min–Maks tiap lagu",
                  foreground="gray", font=("", 8),
                  ).grid(row=16, column=0, columnspan=2, sticky="w", pady=(0, 4))

        ttk.Label(frm, text="Jeda render sebelum download (detik):").grid(row=17, column=0, sticky="w", pady=5)
        self.wait_render_var = tk.IntVar(value=cfg.get("wait_render_sec", 180))
        ttk.Spinbox(frm, from_=60, to=900, increment=30,
                    textvariable=self.wait_render_var, width=8,
                    ).grid(row=17, column=1, sticky="w", padx=(8, 0), pady=5)

        ttk.Label(frm, text="Min ukuran file lagu (KB):").grid(row=18, column=0, sticky="w", pady=5)
        self.min_kb_var = tk.IntVar(value=cfg.get("min_song_kb", 2000))
        ttk.Spinbox(frm, from_=500, to=10000, increment=100,
                    textvariable=self.min_kb_var, width=8,
                    ).grid(row=18, column=1, sticky="w", padx=(8, 0), pady=5)

        self.wait_window()

    def _save(self):
        cfg = load_app_config()
        mode = self.window_mode_var.get()
        cfg["window_mode"]        = mode
        cfg["headless"]           = (mode == "headless")
        cfg["captcha_action"]     = self.captcha_action_var.get()
        cfg["captcha_timeout_sec"]= max(30, int(self.captcha_timeout_var.get() or 120))
        _wmin = max(10, int(self.wait_min_var.get() or 50))
        _wmax = max(10, int(self.wait_max_var.get() or 100))
        if _wmax < _wmin:
            _wmax = _wmin + 10
        cfg["wait_between_min"]   = _wmin
        cfg["wait_between_max"]   = _wmax
        cfg["wait_between_songs"] = _wmin  # backward compat
        cfg["wait_render_sec"]    = max(60,  int(self.wait_render_var.get() or 180))
        cfg["min_song_kb"]        = max(500, int(self.min_kb_var.get() or 2000))
        cfg["window_size"]        = self.window_size_var.get() or "1366x768"
        save_app_config(cfg)
        mode_labels = {"normal": "Normal", "background": "Background (belakang)", "headless": "Headless (invisible)"}
        messagebox.showinfo("Tersimpan",
            f"Runtime settings disimpan!\n\n"
            f"Mode Chrome: {mode_labels.get(mode, mode)}\n"
            f"Captcha: {cfg['captcha_action']} (timeout {cfg['captcha_timeout_sec']}s)\n"
            f"Jeda antar lagu: {cfg['wait_between_min']}s–{cfg['wait_between_max']}s (random)\n"
            f"Jeda render: {cfg['wait_render_sec']}s\n"
            f"Min KB: {cfg['min_song_kb']} KB")
        self.destroy()

# ------------------------------------------------------------------
# Main App
# ------------------------------------------------------------------


# ─────────────────────────────────────────────────────────────────────────────
#  PROMPT MANAGER DIALOG  (v5.38+)
# ─────────────────────────────────────────────────────────────────────────────
class PromptManagerDialog(tk.Toplevel):
    """Dialog untuk membuat dan mengelola multiple custom prompts."""

    _EXAMPLE_TEMPLATE = (
        "You are a professional Smooth R&B and Chill Lofi songwriter.\n"
        "Your task is to write complete song lyrics for song {index} of {total}.\n\n"
        "━━━━━━━━━━━ EDIT BAGIAN INI SESUAI KEBUTUHAN ━━━━━━━━━━━\n\n"
        "GENRE & STYLE: Smooth R&B, Chill Lofi, late-night vibes\n"
        "MOOD: Relaxing, cozy, soulful, peaceful\n\n"
        "LANGUAGE RULES:\n"
        "- Use simple, direct English easy to understand for ages 15-50\n"
        "- Be literal but soulful, use R&B/Lofi vernacular naturally\n"
        "- e.g. \"smooth flow\", \"late night\", \"chill\", \"vibe\", \"unwind\"\n\n"
        "TONE: Influenced by smooth 90s/00s R&B, modern Lofi hip-hop, chillhop\n"
        "PERFECT FOR: studying, midnight relaxation, late drives, rainy nights\n\n"
        "DESCRIPTION / TOPIC: {description}\n"
        "MUSIC STYLE TAGS: {style}\n\n"
        "━━━━━━━━━━━ JANGAN UBAH BAGIAN INI ━━━━━━━━━━━━━━━━━\n\n"
        "SONG STRUCTURE (mandatory):\n"
        "[Instrumental Intro]\n[Verse 1]\n[Chorus]\n[Verse 2]\n[Chorus]\n"
        "[Instrumental Bridge]\n[Chorus]\n[Outro]\n\n"
        "AVAILABLE SUNO SECTION KEYWORDS (always use in square brackets [ ]):\n"
        "Structure : [Intro] [Verse 1] [Verse 2] [Pre-Chorus] [Chorus] [Post-Chorus] [Bridge] [Hook] [Outro]\n"
        "Instrument: [Instrumental Intro] [Instrumental Bridge] [Beat Drop] [Guitar Solo] [Piano Solo] [Sax Solo]\n"
        "Vocal     : [Ad-libs] [Vocal Harmony] [Whisper] [Vocal Fade]\n"
        "Ambiance  : [Fade In] [Fade Out] [Build Up] [Breakdown] [Vinyl Crackle] [Rain Ambience]\n\n"
        "NEGATIVE KEYWORDS (DO NOT include these in lyrics):\n"
        "Themes  : violence, drugs, explicit content, dark depression, anger, hate\n"
        "Words   : scream, shout, fight, kill, die, curse words, explicit slang\n"
        "Style   : fast rap, hard rock energy, aggressive tone, distorted vocals\n"
        "Structure: no talking sections, no spoken word, no rap freestyle breaks\n\n"
        "RULES:\n"
        "- ALWAYS provide TWO different creative song titles (title_b MUST NOT be empty)\n"
        "- ALWAYS provide TWO different song titles (title_a and title_b MUST be different)\n"
        "- Write UNIQUE lyrics different from any other song in this session\n"
        "- MAXIMUM 2000 characters of lyrics. Keep it concise but complete\n"
        "- Use square brackets [] for ALL section tags and music directions\n"
        "- NEVER use parentheses () anywhere in lyrics\n"
        "- Music directions on their OWN line: [Soft Rhodes piano, vinyl crackle]\n\n"
        "Output format (plain text, no JSON, no markdown, no explanation):\n"
        "TITLE_A: First Creative Title\n"
        "TITLE_B: Second Creative Title\n"
        "LYRICS:\n"
        "[Verse 1]\n"
        "line1\n"
        "line2\n"
        "[Chorus]\n"
        "chorus line"
    )

    def __init__(self, parent):
        super().__init__(parent)
        self.title("✍ Prompt Manager")
        self.geometry("1000x680")
        self.minsize(800, 500)
        self.transient(parent)
        self.grab_set()

        self._cfg   = self._load()
        self._dirty = False
        self._cur_idx = 0

        self._build_ui()
        self._refresh_list()
        if self._prompts():
            self._select(0)
        self._apply_mode_ui()

    # ── helpers ──────────────────────────────────────────
    def _prompts(self):
        return self._cfg.setdefault("prompts", [])

    def _load(self):
        try:
            import os, json as _j
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "suno_profile_manager", "prompt_config.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    d = _j.load(f)
                if isinstance(d, dict) and "prompts" in d:
                    return d
        except Exception:
            pass
        return {"active_mode": "default", "active_index": 0, "prompts": []}

    def _save(self):
        try:
            import os, json as _j
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "suno_profile_manager", "prompt_config.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                _j.dump(self._cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Gagal simpan: {e}", parent=self)
            return False

    # ── UI builder ───────────────────────────────────────
    def _build_ui(self):
        # Mode bar
        mode_fr = ttk.Frame(self)
        mode_fr.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(mode_fr, text="Mode:").pack(side="left")
        self._mode_var = tk.StringVar(value=self._cfg.get("active_mode", "default"))
        ttk.Radiobutton(mode_fr, text="● Default (genre otomatis)",
                        variable=self._mode_var, value="default",
                        command=self._on_mode_change).pack(side="left", padx=8)
        ttk.Radiobutton(mode_fr, text="✍ Custom Prompt",
                        variable=self._mode_var, value="custom",
                        command=self._on_mode_change).pack(side="left", padx=8)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        # Main pane
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=0)

        # LEFT — daftar prompt
        left = ttk.Frame(pane, width=200)
        pane.add(left, weight=1)

        ttk.Label(left, text="Daftar Prompt:", font=("", 9, "bold")).pack(anchor="w", pady=(0,4))

        lb_fr = ttk.Frame(left)
        lb_fr.pack(fill="both", expand=True)
        self._lb = tk.Listbox(lb_fr, selectmode="single", activestyle="none",
                              font=("", 9), relief="flat", bd=1,
                              highlightthickness=1)
        sb = ttk.Scrollbar(lb_fr, orient="vertical", command=self._lb.yview)
        self._lb.configure(yscrollcommand=sb.set)
        self._lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._lb.bind("<<ListboxSelect>>", self._on_list_select)

        btn_fr = ttk.Frame(left)
        btn_fr.pack(fill="x", pady=4)
        ttk.Button(btn_fr, text="➕", width=3, command=self._add_prompt).pack(side="left")
        ttk.Button(btn_fr, text="🗑", width=3, command=self._del_prompt).pack(side="left", padx=2)
        ttk.Button(btn_fr, text="⬆", width=3, command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(btn_fr, text="⬇", width=3, command=lambda: self._move(1)).pack(side="left", padx=2)

        # RIGHT — editor
        right = ttk.Frame(pane)
        pane.add(right, weight=4)

        # Nama
        nf = ttk.Frame(right)
        nf.pack(fill="x", pady=(0,6))
        ttk.Label(nf, text="Nama Prompt:").pack(side="left")
        self._name_var = tk.StringVar()
        self._name_entry = ttk.Entry(nf, textvariable=self._name_var, font=("", 10))
        self._name_entry.pack(side="left", fill="x", expand=True, padx=(6,0))

        # System prompt
        ttk.Label(right, text="System Prompt (opsional — biarkan kosong jika tidak perlu):").pack(anchor="w")
        sys_fr = ttk.Frame(right)
        sys_fr.pack(fill="x", pady=(2,8))
        self._sys_txt = tk.Text(sys_fr, height=3, font=("Consolas", 9), wrap="word",
                                relief="solid", bd=1)
        sys_sb = ttk.Scrollbar(sys_fr, orient="vertical", command=self._sys_txt.yview)
        self._sys_txt.configure(yscrollcommand=sys_sb.set)
        self._sys_txt.pack(side="left", fill="x", expand=True)
        sys_sb.pack(side="right", fill="y")

        # User template
        tpl_lbl_fr = ttk.Frame(right)
        tpl_lbl_fr.pack(fill="x")
        ttk.Label(tpl_lbl_fr, text="User Template:", font=("", 9, "bold")).pack(side="left")
        ttk.Label(tpl_lbl_fr,
                  text="  variabel: {description}  {style}  {index}  {total}",
                  foreground="gray", font=("", 8)).pack(side="left")

        tpl_fr = ttk.Frame(right)
        tpl_fr.pack(fill="both", expand=True, pady=(2,6))
        self._tpl_txt = tk.Text(tpl_fr, font=("Consolas", 9), wrap="word",
                                relief="solid", bd=1, undo=True)
        tpl_sb = ttk.Scrollbar(tpl_fr, orient="vertical", command=self._tpl_txt.yview)
        self._tpl_txt.configure(yscrollcommand=tpl_sb.set)
        self._tpl_txt.pack(side="left", fill="both", expand=True)
        tpl_sb.pack(side="right", fill="y")

        # Tombol bawah
        bot = ttk.Frame(right)
        bot.pack(fill="x")
        ttk.Button(bot, text="📋 Isi Contoh Prompt",
                   command=self._fill_example).pack(side="left")
        ttk.Button(bot, text="✅ Jadikan Aktif",
                   command=self._set_active).pack(side="left", padx=6)

        # Footer
        foot = ttk.Frame(self)
        foot.pack(fill="x", padx=10, pady=8)
        ttk.Button(foot, text="💾 Simpan Semua", command=self._save_all).pack(side="left")
        ttk.Button(foot, text="Tutup", command=self._on_close).pack(side="right")
        self._status_lbl = ttk.Label(foot, text="", foreground="green")
        self._status_lbl.pack(side="left", padx=12)

    # ── actions ──────────────────────────────────────────
    def _refresh_list(self):
        self._lb.delete(0, "end")
        ai = self._cfg.get("active_index", 0)
        mode = self._cfg.get("active_mode", "default")
        for i, p in enumerate(self._prompts()):
            marker = " ▶" if (mode == "custom" and i == ai) else ""
            self._lb.insert("end", f"{p.get('name','Prompt '+str(i+1))}{marker}")

    def _select(self, idx):
        ps = self._prompts()
        if not ps or idx < 0 or idx >= len(ps):
            return
        self._flush_current()
        self._cur_idx = idx
        self._lb.selection_clear(0, "end")
        self._lb.selection_set(idx)
        self._lb.see(idx)
        p = ps[idx]
        self._name_var.set(p.get("name", ""))
        self._sys_txt.delete("1.0", "end")
        self._sys_txt.insert("1.0", p.get("system_prompt", ""))
        self._tpl_txt.delete("1.0", "end")
        self._tpl_txt.insert("1.0", p.get("user_template", ""))

    def _flush_current(self):
        ps = self._prompts()
        if not ps or self._cur_idx >= len(ps):
            return
        ps[self._cur_idx]["name"]          = self._name_var.get().strip() or f"Prompt {self._cur_idx+1}"
        ps[self._cur_idx]["system_prompt"] = self._sys_txt.get("1.0", "end-1c").strip()
        ps[self._cur_idx]["user_template"] = self._tpl_txt.get("1.0", "end-1c")

    def _on_list_select(self, _e=None):
        sel = self._lb.curselection()
        if sel:
            self._select(sel[0])

    def _add_prompt(self):
        self._flush_current()
        n = len(self._prompts()) + 1
        self._prompts().append({"name": f"Custom Prompt {n}", "system_prompt": "", "user_template": ""})
        self._refresh_list()
        self._select(len(self._prompts()) - 1)

    def _del_prompt(self):
        ps = self._prompts()
        if not ps:
            return
        self._flush_current()
        if not messagebox.askyesno("Hapus", f"Hapus '{ps[self._cur_idx].get('name')}'?", parent=self):
            return
        ps.pop(self._cur_idx)
        self._cur_idx = max(0, self._cur_idx - 1)
        self._refresh_list()
        if ps:
            self._select(self._cur_idx)
        else:
            self._name_var.set("")
            self._sys_txt.delete("1.0", "end")
            self._tpl_txt.delete("1.0", "end")

    def _move(self, direction):
        ps = self._prompts()
        i  = self._cur_idx
        j  = i + direction
        if j < 0 or j >= len(ps):
            return
        self._flush_current()
        ps[i], ps[j] = ps[j], ps[i]
        if self._cfg.get("active_index") == i:
            self._cfg["active_index"] = j
        elif self._cfg.get("active_index") == j:
            self._cfg["active_index"] = i
        self._cur_idx = j
        self._refresh_list()
        self._select(j)

    def _fill_example(self):
        if messagebox.askyesno("Isi Contoh",
                               "Ganti template saat ini dengan contoh R&B/Lofi?", parent=self):
            self._tpl_txt.delete("1.0", "end")
            self._tpl_txt.insert("1.0", self._EXAMPLE_TEMPLATE)

    def _set_active(self):
        self._flush_current()
        self._cfg["active_mode"]  = "custom"
        self._cfg["active_index"] = self._cur_idx
        self._mode_var.set("custom")
        self._apply_mode_ui()
        self._refresh_list()
        self._status_lbl.config(
            text=f"✅ Aktif: {self._prompts()[self._cur_idx].get('name','?')}")
        self._save()

    def _on_mode_change(self):
        self._cfg["active_mode"] = self._mode_var.get()
        self._apply_mode_ui()
        self._refresh_list()
        self._save()

    def _apply_mode_ui(self):
        is_custom = self._mode_var.get() == "custom"
        state = "normal" if is_custom else "disabled"
        for w in [self._name_entry, self._sys_txt, self._tpl_txt, self._lb]:
            try:
                w.config(state=state)
            except Exception:
                pass

    def _save_all(self):
        self._flush_current()
        self._cfg["active_mode"] = self._mode_var.get()
        if self._save():
            self._status_lbl.config(text="✅ Tersimpan!")
            self._refresh_list()
            self.after(2000, lambda: self._status_lbl.config(text=""))

    def _on_close(self):
        self._flush_current()
        self._cfg["active_mode"] = self._mode_var.get()
        self._save()
        self.destroy()

