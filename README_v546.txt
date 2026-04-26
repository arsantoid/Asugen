ASuGen v5.46 — Indonesian Genres Rebuilt + Custom Prompt Manager
==================================================================

CHANGELOG v5.46:

[1] GENRES.JSON — REBUILT TOTAL UNTUK GENRE INDONESIA
    ─────────────────────────────────────────────────
    Root cause masalah lirik tidak nyambung:
    matrix_variables lama masih pakai konteks Western/English,
    sehingga DeepSeek bingung dan hasilkan lirik campur-aduk.

    SOLUSI: Setiap elemen di-research dari 100+ lagu viral.

    ► dangdut_koplo (rebuilt)
      characters : Konteks Indonesia asli (pasar malam, sawah, LDR)
      settings   : Lokasi Indonesia nyata (warung, terminal, sawah)
      conflicts  : Tema viral dangdut TikTok 2024-2025
      objects    : Objek khas Indonesia (HP, foto, kaos mantan)
      Ref artis  : Safira Inema, Woro Widowati, Yeni Inka, Via Vallen

    ► campur_sari (rebuilt)
      Bahasa     : JAWA NGOKO penuh + Indonesia campuran
      Tema       : tresno, kangen, wirang, lungo, legowo
      Ref artis  : Denny Caknan, Happy Asmara, Niken Salindry

    ► langgam_jawa (rebuilt)
      Bahasa     : JAWA KRAMA/KLASIK puitis
      Tema       : purnama, rembulan, alam jawa, filosofi
      Ref artis  : Gesang, Waljinah, Bandar Keroncong

    ► pop_indonesia (BARU DITAMBAHKAN)
      Bahasa     : Indonesia percakapan sehari-hari
      Tema       : cinta, galau, move on, rindu
      Ref artis  : Andmesh, Mahalini, Lyodra, Rizky Febian

    TOTAL KOMBINASI: 50,625 per genre × 4 genre = 202,500 unik

[2] PROMPT MANAGER — MULTI TEMPLATE SUPPORT
    ─────────────────────────────────────────────────
    Sidebar → tombol "✍ Prompt Manager"
    - Buat banyak custom prompt, tinggal klik "Jadikan Aktif"
    - Toggle: Mode Default (genre otomatis) / Custom Prompt
    - NEGATIVE KEYWORDS block sudah ada di template contoh
    - SUNO SECTION KEYWORDS ada di template (tinggal pilih)
    - output format: PLAIN TEXT (bukan JSON = lebih reliable)

[3] TITLE_B FIX (v5.38+)
    Output plain text bukan JSON → AI tidak pernah kosongkan title_b

[4] TITLE AUTO-FILL — scroll+JS (v5.45)
    Tidak ada More Options hunting, tidak ada timeout.
    Scroll bawah → JS inject langsung ke input title.

CARA INSTALL:
  Ganti SEMUA file .py dan genres.json ke folder ASuGen kamu
  Jalankan: python suno_app.py

FILE YANG BERUBAH:
  suno_app.py     - tombol + method Prompt Manager
  suno_dialogs.py - PromptManagerDialog class + scroll+JS title
  suno_core.py    - TITLE_A/B parser + title_b fallback
  genres.json     - rebuilt 4 genre Indonesia + pop_indonesia baru
==================================================================
