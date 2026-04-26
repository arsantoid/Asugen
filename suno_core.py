# ═══════════════════════════════════════════════════════════════════
#  suno_core.py  —  ASuGen
#  Config, AI generation, Playwright browser engine, download utils
#  Import otomatis dari suno_dialogs.py dan suno_app.py
# ═══════════════════════════════════════════════════════════════════
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

# ── Windows asyncio fix: cegah "Event loop is closed" dari Playwright ──────
import asyncio as _asyncio_fix
import sys as _sys_fix
if _sys_fix.platform == "win32":
    # Playwright di Windows butuh ProactorEventLoop (default di Python 3.8+)
    # tapi perlu policy eksplisit agar subprocess cleanup tidak error
    _asyncio_fix.set_event_loop_policy(_asyncio_fix.WindowsProactorEventLoopPolicy())

def _run_async(coro):
    """Helper asyncio.run() yang aman di Windows + Playwright."""
    import asyncio
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            try:
                # Beri waktu cleanup subprocess Playwright
                loop.run_until_complete(asyncio.sleep(0.1))
            except Exception:
                pass
            loop.close()
    else:
        return asyncio.run(coro)

# Semua folder relatif terhadap lokasi script ini → portable, pindah harddisk langsung jalan
APP_DIR = (Path(__file__).parent / "suno_profile_manager").resolve()
DATA_DIR = APP_DIR / "profiles"
CONFIG_FILE = APP_DIR / "profiles.json"
AI_CONFIG_FILE = APP_DIR / "ai_config.json"
APP_CONFIG_FILE  = APP_DIR / "app_config.json"
PROMPT_CFG_FILE  = APP_DIR / "prompt_config.json"   # Multi custom prompt
SONGS_DIR    = Path(__file__).parent / "suno_songs"  # folder download lagu
GENRES_FILE       = Path(__file__).parent / "genres.json"  # genre mapping eksternal
DEEPSEEK_WEB_URL  = "https://chat.deepseek.com"            # DeepSeek web chat

DEFAULT_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

SUNO_URL = "https://suno.com"
MAX_CREATES = 5
FREE_CREDITS_PER_CREATE = 10
ASSUMED_CREDITS_PER_PROFILE = 50
MAX_SONGS_PER_PROFILE = 5          # maks 5 lagu per profil per hari  # bulk: setiap profile dianggap punya 50 kredit
MIN_FULL_SONG_KB = 2000   # file < 2000 KB dianggap preview/clip, skip
MIN_LYRICS_CHARS = 1500  # lirik < 1500 karakter dianggap gagal -> retry

_stop_requested  = threading.Event()
stop_requested   = _stop_requested   # public alias
_pause_requested = threading.Event() # pause: berhenti sementara, Chrome tetap buka

def request_pause():
    """Set pause — automation dijeda, Chrome tidak ditutup."""
    _pause_requested.set()

def resume_generate():
    """Clear pause — lanjutkan automation."""
    _pause_requested.clear()

def is_paused() -> bool:
    return _pause_requested.is_set()

def wait_if_paused(interval: float = 0.5):
    """Block sampai resume. Cek stop tiap interval agar tidak hang."""
    while _pause_requested.is_set():
        if _stop_requested.is_set():
            break
        threading.Event().wait(interval)

def get_stop_event() -> threading.Event:
    """Selalu kembalikan singleton _stop_requested dari suno_core."""
    return _stop_requested

def request_stop():
    """Set stop flag — thread-safe dari manapun."""
    _stop_requested.set()
    _pause_requested.clear()  # auto-resume agar tidak hang saat stop

def clear_stop():
    """Clear stop flag — panggil sebelum mulai generate baru."""
    _stop_requested.clear()
    _pause_requested.clear()

def is_stop_requested() -> bool:
    """Cek apakah stop diminta."""
    return _stop_requested.is_set()

def save_window_position(profile_dir: str, x: int, y: int):
    """Simpan posisi window Chrome terakhir per-profile ke browser_cfg.json."""
    try:
        cfg_path = Path(profile_dir) / "browser_cfg.json"
        cfg = {}
        if cfg_path.exists():
            try: cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception: pass
        cfg["window_x"] = int(x); cfg["window_y"] = int(y)
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

def load_window_position(profile_dir: str):
    """Load posisi window Chrome terakhir. Return (x, y) atau None."""
    try:
        cfg_path = Path(profile_dir) / "browser_cfg.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            x = cfg.get("window_x"); y = cfg.get("window_y")
            if x is not None and y is not None:
                return int(x), int(y)
    except Exception:
        pass
    return None




# ------------------------------------------------------------------
# AI Config
# ------------------------------------------------------------------

# OpenRouter free model chain — urutan prioritas fallback (updated April 2026)
# Sumber real-time: https://openrouter.ai/collections/free-models
# Urutan: volume usage tertinggi + terbukti follow structured output instructions
OPENROUTER_FREE_MODELS = [
    # ── PRIORITAS UTAMA: berbayar tapi murah & trial-friendly ──
    "openai/gpt-4o-mini",                      # #1  — PRIORITAS: murah, trial OK, kualitas lirik terbaik ✓
    "google/gemini-2.0-flash-lite-001",        # #2  — murah, cepat, kualitas bagus (Gemini Flash Lite)
    "google/gemini-2.0-flash-001",             # #3  — sedikit lebih mahal, hasil lebih kaya
    "openai/gpt-4.1-nano",                     # #4  — model terbaru OpenAI, sangat murah
    "anthropic/claude-haiku-4-5",              # #5  — Claude Haiku, murah, kreatif
    "mistralai/mistral-small-3.2-24b-instruct",# #6  — Mistral Small, murah, multilingual bagus
    # ── FALLBACK GRATIS: pakai jika model berbayar error/limit ──
    "openai/gpt-oss-120b:free",                # #7  — gratis, 65B tokens, terbukti berhasil ✓
    "arcee-ai/arcee-trinity-large:free",       # #8  — gratis, 143B tokens, creative writing kuat
    "z-ai/glm-4.5-air:free",                   # #9  — gratis, 92B tokens, multilingual ID/EN
    "openrouter/optimus-alpha:free",           # #10 — gratis, Elephant 100B, follow instruksi
    "google/gemma-4-31b-it:free",              # #11 — gratis, 18.7B tokens, 262K ctx
    "nvidia/nemotron-nano-30b-a3b:free",       # #12 — gratis, cepat
    "qwen/qwen3-next-80b-a3b-instruct:free",   # #13 — gratis, stabil multilingual
    "openai/gpt-oss-20b:free",                 # #14 — gratis, ringan
    "meta-llama/llama-3.3-70b-instruct:free",  # #15 — gratis, sering 429, fallback
    "openrouter/free",                         # #16 — auto-router fallback terakhir
]

DEFAULT_AI_CONFIG = {
    "api_key":    "",
    "api_keys":   [],   # multi-key untuk auto-rotate
    "base_url":   "https://openrouter.ai/api/v1",
    "model":      OPENROUTER_FREE_MODELS[0],
    "_key_index": 0,
}


def load_ai_config() -> dict:
    ensure_dirs()
    try:
        if AI_CONFIG_FILE.exists():
            return {**DEFAULT_AI_CONFIG, **json.loads(AI_CONFIG_FILE.read_text(encoding="utf-8"))}
    except Exception:
        pass
    return DEFAULT_AI_CONFIG.copy()


def save_ai_config(cfg: dict):
    ensure_dirs()
    AI_CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------
# AI API call — OpenAI-compatible + Anthropic Claude native
# ------------------------------------------------------------------

def load_app_config() -> dict:
    ensure_dirs()
    defaults = {
        "chrome_path": "",
        "headless": False,
        "wait_between_songs": 90,
        "wait_between_min": 50,
        "wait_between_max": 100,
        "wait_render_sec": 180,
        "min_song_kb": 2000,
    }
    try:
        if APP_CONFIG_FILE.exists():
            return {**defaults, **json.loads(APP_CONFIG_FILE.read_text(encoding="utf-8"))}
    except Exception:
        pass
    return defaults.copy()


def save_app_config(cfg: dict):
    ensure_dirs()
    APP_CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ══ Multi Custom Prompt Config ═══════════════════════════════════════════════
# Struktur: list of prompt dicts → bisa simpan banyak prompt, pilih lewat UI
_DEFAULT_PROMPT_CFG = {
    "mode": "default",      # "default" | "custom"
    "active_index": 0,      # index prompt custom yang aktif
    "prompts": [
        {
            "label":     "Custom Prompt 1",
            "system":    "",
            "template":  "",
        }
    ],
}

def load_prompt_config() -> dict:
    """Load multi-prompt config. Merge dengan default agar backward-compat."""
    ensure_dirs()
    try:
        if PROMPT_CFG_FILE.exists():
            raw = json.loads(PROMPT_CFG_FILE.read_text(encoding="utf-8"))
            merged = dict(_DEFAULT_PROMPT_CFG)
            merged.update(raw)
            # Pastikan key 'prompts' adalah list
            if not isinstance(merged.get("prompts"), list) or not merged["prompts"]:
                merged["prompts"] = list(_DEFAULT_PROMPT_CFG["prompts"])
            # FIX v5.44: Selalu mulai dalam mode Default saat buka app
            # Prompt yang dibuat tetap tersimpan, hanya mode-nya di-reset
            merged["mode"] = "default"
            return merged
    except Exception:
        pass
    return dict(_DEFAULT_PROMPT_CFG)

def save_prompt_config(cfg: dict):
    ensure_dirs()
    PROMPT_CFG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def get_active_prompt() -> dict:
    """Kembalikan prompt dict yang aktif. Return {} jika mode=default."""
    cfg = load_prompt_config()
    if cfg.get("mode") != "custom":
        return {}
    prompts = cfg.get("prompts", [])
    idx = int(cfg.get("active_index", 0))
    if not prompts:
        return {}
    idx = max(0, min(idx, len(prompts) - 1))
    return prompts[idx]

def _safe_prompt_format(template: str, description: str, style: str, index: int, total: int) -> str:
    """Ganti {description} {style} {index} {total} SAJA, abaikan { } lain (JSON dll)."""
    result = template
    result = result.replace("{description}", description)
    result = result.replace("{style}",       style)
    result = result.replace("{index}",       str(index))
    result = result.replace("{total}",       str(total))
    return result

def _generate_title_b(title_a: str, song_index: int = 1) -> str:
    """Generate title_b yang natural dari title_a jika AI tidak kasih."""
    import random as _rnd
    _rnd.seed(hash(title_a + str(song_index)) % 2**32)
    suffixes = [
        "Late Night Mix", "Midnight Version", "Slow Burn",
        "After Hours", "Chill Edit", "Soft Version",
        "Rainy Mix", "Lo-Fi Edit", "Night Drive",
    ]
    return f"{title_a} - {_rnd.choice(suffixes)}"
# ═════════════════════════════════════════════════════════════════════════════


_genres_cache: dict = {}


def load_genres() -> dict:
    """Load genre mapping dari genres.json (eksternal, bisa diedit user).
    Cache di memory agar tidak baca file setiap generate."""
    global _genres_cache
    if _genres_cache:
        return _genres_cache
    if GENRES_FILE.exists():
        try:
            with open(GENRES_FILE, encoding="utf-8") as f:
                _genres_cache = json.load(f)
            return _genres_cache
        except Exception:
            pass
    return {}  # fallback: kosong -> pakai generic guide


def reload_genres():
    """Paksa reload genres.json (hapus cache), berguna jika user edit file."""
    global _genres_cache
    _genres_cache = {}
    return load_genres()


# ------------------------------------------------------------------
# DeepSeek Web Mode - generate lirik via browser (tanpa API key)
# SYARAT: Login ke chat.deepseek.com di profil Chrome yang dipakai
# ------------------------------------------------------------------

async def _deepseek_web_generate_lyrics(context, prompt, log_cb, timeout_sec=120):
    import asyncio, time as _tm
    log_cb("[DS-WEB] Membuka tab DeepSeek...")
    page = await context.new_page()
    result_text = ""
    try:
        await page.goto(DEEPSEEK_WEB_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        for csel in ["button[aria-label*='close' i]", "button:has-text('Close')",
                     "button:has-text('Got it')", "button:has-text('OK')"]:
            try:
                btn = await page.query_selector(csel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(1)
                    break
            except Exception:
                pass
        input_sel = None
        INPUT_SELS = [
            "textarea#chat-input",
            "textarea[placeholder*='Message' i]",
            "textarea[placeholder*='Send' i]",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
            "textarea",
        ]
        for sel in INPUT_SELS:
            try:
                el = await page.wait_for_selector(sel, timeout=7000, state="visible")
                if el:
                    input_sel = sel
                    log_cb(f"[DS-WEB] Input ditemukan: {sel}")
                    break
            except Exception:
                continue
        if not input_sel:
            log_cb("[DS-WEB] GAGAL: Input tidak ditemukan. Pastikan sudah login DeepSeek.")
            return ""
        log_cb("[DS-WEB] Mengirim prompt...")

        # Pakai locator agar tidak kena stale ElementHandle saat DOM DeepSeek re-render
        loc = page.locator(input_sel).first
        try:
            await loc.wait_for(state="visible", timeout=5000)
            await loc.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass

        try:
            if "contenteditable" in input_sel:
                await page.evaluate(
                    "(sel, t) => { const el = document.querySelector(sel); if (!el) return; el.focus(); el.textContent = t; el.dispatchEvent(new InputEvent('input', {bubbles: true})); }",
                    input_sel, prompt)
            else:
                await loc.fill("")
                await asyncio.sleep(0.2)
                await page.evaluate(
                    "(args) => { const el = document.querySelector(args.sel); if (!el) return; const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; setter.call(el, args.text); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
                    {"sel": input_sel, "text": prompt}
                )
        except Exception as fill_err:
            log_cb(f"[DS-WEB] Fill error: {fill_err} - coba keyboard fallback")
            try:
                loc2 = page.locator(input_sel).first
                await loc2.click()
                await asyncio.sleep(0.3)
                for chunk_i in range(0, len(prompt), 300):
                    await loc2.type(prompt[chunk_i:chunk_i + 300], delay=5)
                    await asyncio.sleep(0.1)
            except Exception as kb_err:
                log_cb(f"[DS-WEB] Keyboard fallback juga gagal: {kb_err}")
                return ""

        await asyncio.sleep(1.0)
        sent = False
        for ssel in ["button[aria-label*='send' i]", "button[type='submit']",
                     "[data-testid*='send' i]", "button:has(svg):last-of-type"]:
            try:
                sb_loc = page.locator(ssel).last
                if await sb_loc.is_visible() and await sb_loc.is_enabled():
                    await sb_loc.click()
                    sent = True
                    log_cb("[DS-WEB] Terkirim via tombol Send.")
                    break
            except Exception:
                continue
        if not sent:
            await page.keyboard.press("Enter")
            log_cb("[DS-WEB] Terkirim via Enter.")
        log_cb(f"[DS-WEB] Menunggu respons (max {timeout_sec}s)...")
        t0 = _tm.time()
        prev_len = 0
        stable_count = 0
        STABLE_NEEDED = 4
        while True:
            elapsed = _tm.time() - t0
            if elapsed > timeout_sec:
                log_cb(f"[DS-WEB] Timeout {timeout_sec}s - ambil teks yang ada.")
                break
            loading = False
            for lsel in ["button[aria-label*='stop' i]", "button:has-text('Stop')",
                         "[class*='loading' i]", "[class*='spinner' i]",
                         "[data-testid*='stop' i]"]:
                try:
                    el = await page.query_selector(lsel)
                    if el and await el.is_visible():
                        loading = True
                        break
                except Exception:
                    pass
            cur = ""
            for rsel in [".ds-markdown", "[class*='markdown' i]",
                         "[class*='message-content' i]", "[class*='prose' i]",
                         "[class*='assistant' i] [class*='content' i]"]:
                try:
                    els = await page.query_selector_all(rsel)
                    if els:
                        t = (await els[-1].inner_text()).strip()
                        if len(t) > len(cur):
                            cur = t
                except Exception:
                    continue
            if loading:
                log_cb(f"[DS-WEB] Generating... {len(cur)} char ({int(elapsed)}s)")
                await asyncio.sleep(2.5)
                stable_count = 0
                prev_len = len(cur)
                continue
            if len(cur) > 0 and len(cur) == prev_len:
                stable_count += 1
                if stable_count >= STABLE_NEEDED:
                    log_cb(f"[DS-WEB] Stabil ({len(cur)} char, {int(elapsed)}s)")
                    result_text = cur
                    break
            else:
                stable_count = 0
            prev_len = len(cur)
            await asyncio.sleep(2.5)
        if not result_text:
            for rsel in [".ds-markdown", "[class*='markdown' i]", "[class*='prose' i]"]:
                try:
                    els = await page.query_selector_all(rsel)
                    if els:
                        result_text = (await els[-1].inner_text()).strip()
                        if result_text:
                            break
                except Exception:
                    continue
        if result_text:
            log_cb(f"[DS-WEB] Berhasil: {len(result_text)} karakter diterima.")
        else:
            log_cb("[DS-WEB] GAGAL: Respons kosong. Pastikan sudah login DeepSeek.")
    except Exception as e:
        log_cb(f"[DS-WEB] Error: {e}")
    finally:
        try:
            await page.close()
            log_cb("[DS-WEB] Tab DeepSeek ditutup.")
        except Exception:
            pass
    return result_text


def _parse_deepseek_response(raw):
    """Parse DeepSeek response. Support TITLE_A/TITLE_B (format baru) dan TITLE (format lama)."""
    title_a = title_b = style_out = ""
    lyrics_lines = []
    in_lyrics = False
    for line in raw.strip().splitlines():
        s = line.strip(); su = s.upper()
        if not in_lyrics:
            if su.startswith("TITLE_A:"):   title_a = s[8:].strip().strip("\"'")
            elif su.startswith("TITLE_B:"): title_b = s[8:].strip().strip("\"'")
            elif su.startswith("TITLE:") and not title_a: title_a = s[6:].strip().strip("\"'")
            elif su.startswith("STYLE:"):   style_out = s[6:].strip().strip("\"'")
            elif su.startswith("LYRICS:") or su == "LYRICS": in_lyrics = True
        else:
            lyrics_lines.append(line)
    lyrics = "\n".join(lyrics_lines).strip() or raw.strip()
    if not title_a:
        first = [l.strip() for l in raw.splitlines() if l.strip()]
        title_a = first[0][:60] if first else "Untitled"
    if not title_b:
        w = title_a.split()
        title_b = _generate_title_b(title_a)
    return {"title": title_a, "title_a": title_a, "title_b": title_b,
            "style": style_out, "lyrics": lyrics}

def _sanitize_lyrics(lyrics: str) -> str:
    """
    1. Semua () → [] tanpa kecuali
    2. Baris instrumen/musik plaintext → dibungkus [...]
    3. Semua baris di [Outro] / [Intro] / [Instrumental Break] → dibungkus [...]
    """
    import re as _re

    _SPEC = {
        "guitar","bass","drum","drums","piano","violin","cello","synth","pad",
        "acoustic","electric","fingerpick","fingerpicking","strum","pluck","solo",
        "harmonica","trumpet","saxophone","sax","flute","horn","choir",
        "reverb","sample","loop","riff","ambient","arpeggio","picking","mic",
        "muffled","sparse","layered","wah","tremolo","distortion","overdriven",
        "pedal","delay","arpeggiated","plucked","bowed","banjo","mandolin",
        "ukulele","sitar","tabla","conga","bongo","marimba","xylophone","celesta",
        "harpsichord","organ","accordion","bassoon","clarinet","tuba","trombone",
        "snare","kick","hihat","cymbal","shaker","tambourine","pulsing",
        "detuned","detune","fingerpicked","humming","hum","fading","crackle",
        "crackles","slowing","building","continues","footstep","footsteps",
        "gravel","whisper","whispering","breathing","exhale","sigh","rustle",
        "breath","strings","fingers","tapping","taps","strumming","strums",
        "plucking","picking","melody","melodies","chord","chords","note","notes",
        "tune","tuning","ringing","fades","swells","rises","fades out",
        "clicks","claps","clapping","stomp","stomping","tap",
    }
    _LYRIC = {
        "collect","morning","light","dark","night","day","sky","rain","sun",
        "heart","soul","love","dream","life","time","world","face","hand",
        "eye","eyes","voice","word","words","door","window","floor","wall",
        "memory","forget","remember","walk","run","stand","fall","rise",
        "sleep","wake","feel","feels","know","knew","tell","say","said",
        "cry","tears","smile","laugh","miss","lost","find","found",
        "leave","left","stay","come","go","gone","back","old","new","last",
        "first","cold","warm","empty","full","still","quiet","alone","together",
        "always","never","maybe","only","once","again","away","down","across",
        "between","before","after","through","city","street","road","house",
        "home","room","town","river","clock","year","month","hour","moment",
        "place","name","letter","story","color","shadow","hope","fear","pain",
        "fire","water","stone","glass","paper","dust","smoke",
    }
    _PRON = [" i "," i'"," my "," me "," you "," your "," we ",
             " she "," he "," they "," her "," him "," us "," our "]
    # Section yang seluruh isinya adalah direction → wrap semua baris
    _DIR_SECTIONS = {"outro","instrumental break","instrumental","intro","interlude"}

    def _looks_music(line):
        l = line.lower()
        w = set(_re.sub(r'[^a-z ]', ' ', l).split())
        m = w & _SPEC
        if not m: return False
        if any(p in " " + l + " " for p in _PRON): return False
        lw = w & _LYRIC
        if len(lw) >= len(m) + 2: return False
        return True

    lines_out = []
    cur_section = ""

    for line in lyrics.splitlines():
        s = line.strip()
        if not s:
            lines_out.append(""); continue

        # Deteksi section tag
        sec_m = _re.match(r'^\[([^\]]+)\]$', s)
        if sec_m:
            cur_section = sec_m.group(1).lower()
            lines_out.append(line); continue

        # 1. Seluruh baris (...) → [...]
        m1 = _re.fullmatch(r'\((.+)\)', s)
        if m1:
            inner = m1.group(1).strip()
            inner = inner[0].upper() + inner[1:] if inner else inner
            lines_out.append(f"[{inner}]"); continue

        # 2. [Tag] (...) dalam 1 baris → [Tag - ...]
        m2 = _re.match(r'^(\[[^\]]+\])\s+\((.+)\)\s*$', s)
        if m2:
            tag = m2.group(1)[:-1]
            lines_out.append(f"{tag} - {m2.group(2).strip()}]"); continue

        # 3. () di dalam [...] → hapus kurungnya
        line = _re.sub(r'\[([^\]]*?)\(([^)]+)\)([^\]]*)\]',
                       lambda m: f"[{m.group(1)}{m.group(2)}{m.group(3)}]", line)

        # 4. () di mana saja → [...]
        line = _re.sub(r'\(([^)]+)\)', lambda m: f"[{m.group(1).strip()}]", line)

        s2 = line.strip()
        already_bracket = s2.startswith('[') and s2.endswith(']')

        # 5. Section direction ([Outro]/[Intro]/[Instrumental Break]) → wrap semua baris
        if any(ds in cur_section for ds in _DIR_SECTIONS):
            if not already_bracket:
                line = f"[{s2}]"
            lines_out.append(line); continue

        # 6. Baris plaintext berisi instrumen di section lain
        if not already_bracket and _looks_music(s2):
            line = f"[{s2}]"

        lines_out.append(line)

    # Strip label rima A/B yang ikut tertulis DeepSeek di akhir baris
    _AB_PAT = re.compile(r'\s+[AB]\s*$', re.IGNORECASE)
    lines_out = [
        _AB_PAT.sub("", ln) if not ln.strip().startswith("[") else ln
        for ln in lines_out
    ]

    return "\n".join(lines_out)



async def _deepseek_web_prepare_songs(context, config, log_cb, timeout_sec=120):
    import asyncio
    description  = config.get("description", "")
    quantity     = config.get("quantity", 1)
    instrumental = config.get("instrumental", False)
    _lyric_source = config.get("lyric_source", "deepseek_web")
    _is_mini     = (_lyric_source == "deepseek_web_mini")  # Mini: verse+outro only, no min chars
    # "description" adalah key dari GenerateDialog & BulkCreateDialog
    # "style_override" hanya dipakai di path lama — fallback ke description
    style_input  = (config.get("style_override", "") or config.get("description", "")).strip()
    _language    = (config.get("language", "") or "").strip()
    _sl = (style_input or "").lower()  # style only, tanpa description
    # ── Version marker (visible di terminal) ───────────────────────────────
    _log_style = (style_input or "")[:50]
    print(f"[ASuGen v5.40.1] _deepseek_web_prepare_songs | style='{_log_style}...'")
    _genre_db = load_genres()
    _genre_guide = ""
    _detected_style = style_input or ""
    import random as _rand

    # ── Deteksi genre dari 2-4 frasa/kata PERTAMA style (split koma) ──────────
    # Logika: split style by koma → cek frasa [0],[1],[2],[3] dari kiri
    # Frasa pertama yang mengandung keyword genre = pemenang
    # Tidak pakai description sama sekali
    _sl_full = (style_input or "").lower().strip()

    # Kumpulkan semua keyword → list, sort terpanjang dulu
    _all_kw_genre = []
    for _gname, _gdata in _genre_db.items():
        for _kw in _gdata.get("keywords", []):
            _all_kw_genre.append((_kw, _gname))
    _all_kw_genre.sort(key=lambda x: len(x[0]), reverse=True)

    def _detect_by_comma_parts(sl, kw_list, max_parts=4):
        """Split by koma, cek tiap frasa dari kiri. Return genre pertama yang match."""
        parts = [p.strip() for p in sl.split(",")]
        for part in parts[:max_parts]:
            for _kw, _gn in kw_list:
                if _kw in part:
                    return _gn
        # Fallback: 4 kata pertama
        four_words = " ".join(sl.split()[:4])
        for _kw, _gn in kw_list:
            if _kw in four_words:
                return _gn
        return None

    _matched_genre_key = _detect_by_comma_parts(_sl_full, _all_kw_genre)

    # Fallback: random genre
    if not _matched_genre_key:
        _matched_genre_key = _rand.choice(list(_genre_db.keys()))

    print(f"[ASuGen] Genre detected: '{_matched_genre_key}' | style_start='{(_sl_full[:40])}'")
    _matched_genre_data = _genre_db.get(_matched_genre_key, {})
    _genre_guide = _matched_genre_data.get("guide", "") or (
        f"Music style: {style_input or description}. "
        "Write lyrics that perfectly match this style's mood, energy, and culture."
    )
    _detected_style = _matched_genre_key.replace("_", " ").title()
    _mv              = _matched_genre_data.get("matrix_variables", {})
    _mv_characters   = _mv.get("characters", [])
    _mv_settings     = _mv.get("settings", [])
    _mv_conflicts    = _mv.get("conflicts", [])
    _mv_objects      = _mv.get("objects_of_focus", [])
    _genre_emotions  = _matched_genre_data.get("emotions", [])
    _genre_vocal     = _matched_genre_data.get("vocal_style", "")
    _genre_lstruct   = _matched_genre_data.get("lyric_structure", "")

    _use_matrix  = bool(_mv_characters and _mv_settings and _mv_conflicts and _mv_objects)
    _song_topics = [] if _use_matrix else _matched_genre_data.get("topics", [])

    _available_topics = list(_song_topics)
    if not _use_matrix:
        if len(_available_topics) < quantity:
            for _gd in _genre_db.values():
                for _t in _gd.get("topics", []):
                    if _t not in _available_topics:
                        _available_topics.append(_t)
        _rand.shuffle(_available_topics)
    else:
        _matrix_combos = []
        for _ in range(quantity):
            _matrix_combos.append({
                "character": _rand.choice(_mv_characters),
                "setting"  : _rand.choice(_mv_settings),
                "conflict" : _rand.choice(_mv_conflicts),
                "object"   : _rand.choice(_mv_objects),
            })

    songs = []
    for i in range(1, quantity + 1):
        if _stop_requested.is_set():
            break
        log_cb(f"[DS-WEB] [{i}/{quantity}] Membuat lirik lagu ke-{i}...")
        # STYLE di output = input user verbatim (bukan nama genre DB)
        detected = style_input or _detected_style or 'pop, emotional, female vocal'
        if _use_matrix and _matrix_combos:
            _mx      = _matrix_combos[i-1] if i-1 < len(_matrix_combos) else _rand.choice(_matrix_combos)
            _mx_char    = _mx["character"]
            _mx_setting = _mx["setting"]
            _mx_conflict= _mx["conflict"]
            _mx_object  = _mx["object"]
            _topic = (
                f"{_mx_char} located in {_mx_setting}. "
                f"They are {_mx_conflict}."
            )
        else:
            _mx_char = _mx_setting = _mx_conflict = _mx_object = ""
            _topic = (_available_topics[i-1]
                      if _available_topics and i-1 < len(_available_topics)
                      else (description or style_input))
        _instr_note = (
            "THIS IS AN INSTRUMENTAL SONG. Do NOT write any lyrics.\n"
            "Leave the LYRICS section COMPLETELY EMPTY (just write the tag).\n"
        ) if instrumental else ""

        # FIX: Deteksi lofi → aktifkan semi-instrumental mode
        # FIX: deteksi lofi HANYA dari style_input bukan description
        _style_lower = (style_input or "").lower()
        _is_lofi = any(kw in _style_lower for kw in ["lofi", "lo-fi", "lo fi", "chillhop", "chill hop", "study beats", "chill beats"])
        _lofi_note = ""
        _lofi_style_extra = ""
        _song_structure = (
            _genre_lstruct if _genre_lstruct
            else (
                "[Verse 1] → [Pre-Chorus](opt) → [Chorus] → [Verse 2] → [Pre-Chorus](opt)\n"
                "→ [Chorus] → [Instrumental Break] → [Bridge] → [Final Chorus] → [Outro]\n"
                "NEVER start with [Intro] or [Instrumental]. [Instrumental Break] AFTER 2nd Chorus ONLY."
            )
        )
        if _is_lofi and not instrumental:
            _lofi_note = (
                "⚠️ SEMI-INSTRUMENTAL MODE (LOFI STUDY):\n"
                "OUTPUT FORMAT: Write ONLY the raw lyrics/tags. NO explanations, NO comments, NO markdown, NO asterisks.\n"
                "START directly with the first section tag. Example output format:\n"
                "[Intro - instrumental]\n"
                "[Verse]\n"
                "Rain on the window, coffee going cold\n"
                "Pages half-read, stories left untold\n"
                "[Instrumental Break]\n"
                "[Humming]\n"
                "[Chorus]\n"
                "Still here, still breathing\n"
                "[Instrumental Break]\n"
                "[Outro - instrumental]\n"
                "--- END EXAMPLE ---\n"
                "RULES:\n"
                "- ONLY use square brackets [] for section tags. NEVER parentheses ().\n"
                "- Vocal lines: [Verse] max 4 lines, [Chorus] max 2 lines. ALL other sections = [Instrumental] tags.\n"
                "- Use 4-6 section tags total. Keep it SHORT and sparse — lofi is minimal.\n"
                "- MAXIMUM 8 vocal lines total across ALL [Verse] and [Chorus] sections combined.\n"
                "- RHYME SCHEME: Verse=ABAB(1&3 rhyme,2&4 rhyme),Chorus=AABB. NEVER write A/B labels in output!\n"
                "  No orphan lines — every vocal line must have a rhyme partner.\n"
                "  Near-rhyme OK (night/light, stay/away). Natural flow over forced rhyme.\n"
                "- Do NOT explain, do NOT add notes, JUST write the lyrics/tags directly.\n\n"
            )
            _lofi_style_extra = ", minimal vocals, mostly instrumental, sparse lyrics, long instrumental breaks, soft humming, ambient, extended outro"
            _song_structure = (
                "[Intro - instrumental] → [Verse 1](2-4 lines only) → [Instrumental Break]\n"
                "→ [Chorus](1-2 lines only) → [Instrumental Break] → [Verse 2](2-4 lines only)\n"
                "→ [Instrumental Break] → [Chorus](1-2 lines) → [Outro - instrumental]\n"
                "MOST sections MUST be [Instrumental] tags — NO extra lyric lines outside Verse/Chorus."
            )

        # ── MINI LYRICS MODE ⚡ ───────────────────────────────────────────
        # Verse 1, Verse 2 + Outro dapat lirik; semua bagian lain instrumental
        if _is_mini and not instrumental:
            _lofi_note = (
                "⚡ MINI LYRICS MODE:\n"
                "ONLY these sections get real vocal lyrics:\n"
                "  [Verse 1] — 4 lines MAX\n"
                "  [Verse 2] — 4 lines MAX\n"
                "  [Outro]   — 2 lines MAX (fade/close)\n"
                "ALL other sections ([Chorus], [Bridge], [Pre-Chorus], [Intro], [Hook])\n"
                "MUST use ONLY instrumental/music direction tags — NO vocal lines.\n"
                "Example:\n"
                "  [Chorus]\n"
                "  [Instrumental - full band, building]\n"
                "  [Bridge]\n"
                "  [Instrumental Break]\n"
                "Total vocal lines: MAX 10 lines across ALL sections combined.\n"
                "- RHYME SCHEME (MANDATORY): Verse=ABAB, Chorus=AABB. CRITICAL: NEVER print A/B markers in lyrics!\n"
                "  Outro = AA couplet (2 lines that rhyme, closing feel).\n"
                "  Near-rhyme OK (night/light, stay/way). Natural over forced.\n"
                "Do NOT write explanations. Output only lyrics/tags directly.\n\n"
            )
            _lofi_style_extra = ", minimal vocals, instrumental chorus, instrumental bridge, verse-focused"
            _song_structure = (
                "[Instrumental Intro] → [Verse 1](4 lines vocal) → [Chorus - instrumental]\n"
                "→ [Verse 2](4 lines vocal) → [Chorus - instrumental]\n"
                "→ [Instrumental Bridge] → [Chorus - instrumental]\n"
                "→ [Outro](2 lines vocal, then fade)\n"
                "RULE: Chorus, Bridge, Intro = NO vocal lines. Use [Instrumental ...] tags only."
            )
        # ─────────────────────────────────────────────────────────────────

        # Susun bagian matrix tema (hanya jika pakai matrix_variables)
        _matrix_section = ""
        if _use_matrix and _mx_char:
            _emotions_str = ", ".join(_genre_emotions) if _genre_emotions else ""
            _matrix_section = (
                f"VOCAL STYLE: {_genre_vocal}\n" if _genre_vocal else ""
            ) + (
                f"EMOTIONS: {_emotions_str}\n" if _emotions_str else ""
            ) + (
                "\nSONG THEME:\n"
                f"Character: {_mx_char}\n"
                f"Setting: {_mx_setting}\n"
                f"Conflict: {_mx_conflict}\n"
                f"Focus object (mention poetically): {_mx_object}\n\n"
                "RULES:\n"
                "1. Do NOT use clichés (neon lights, dancing in the rain, toxic, warrior, phoenix, ethereal).\n"
                "2. Provide 2 unique song title ideas (max 3-4 words each, concrete and specific).\n"
                "3. Do NOT repeat verse lines verbatim.\n"
            )

        _lang_note = (
            f"LANGUAGE: Write ALL lyrics STRICTLY in {_language}.\n"
            "Section tags stay in English ([Verse 1], [Chorus], etc).\n"
            "Do NOT mix languages unless the description explicitly requests it.\n\n"
        ) if _language else ""
        # ══ Custom Prompt Mode (DeepSeek Web) ══════════════════════════════════
        _active_p_ds = get_active_prompt()
        if _active_p_ds and _active_p_ds.get("template", "").strip():
            _ctpl_ds = _active_p_ds["template"]
            _csys_ds = _active_p_ds.get("system", "").strip()
            prompt = _safe_prompt_format(
                _ctpl_ds,
                description=description,
                style=style_input or description,
                index=i,
                total=quantity,
            )
            if _csys_ds:
                prompt = _csys_ds + "\n\n" + prompt
            log_cb(f"[CUSTOM PROMPT] '{_active_p_ds.get('label','Custom')}' lagu {i}/{quantity}")
        else:
            # ── Default prompt bawaan ASuGen ─────────────────────────────────
            prompt = (
                f"You are a professional songwriter. Write song #{i} of {quantity}.\n\n"
            f"GENRE DIRECTIVE: {_genre_guide}\n\n"
            f"SONG STRUCTURE: {_song_structure}\n\n"
            f"TOPIC / DESCRIPTION: {_topic}\n\n"
            f"{_matrix_section}"
            f"{_instr_note}"
            f"{_lang_note}"
            f"{_lofi_note}"
            "OUTPUT: Write ONLY the raw lyrics. NO explanations, NO comments, NO markdown, NO asterisks before section tags.\n"
            "Start DIRECTLY with the first section tag like [Verse 1].\n"
            "REQUIREMENTS:\n"
            f"- Style tags for Suno AI: {style_input or _detected_style or 'match the genre above'}{_lofi_style_extra}\n"
            "- Song structure: [Verse 1], [Chorus], [Verse 2], [Bridge], [Outro]\n"
            f"- {('MINI MODE: verse+outro only. MAX 10 vocal lines total. NO chorus vocals.' if _is_mini else 'LOFI: keep lyrics SHORT and sparse. MAX 8 vocal lines total.' if _is_lofi else f'MINIMUM {MIN_LYRICS_CHARS} characters of raw lyrics+tags (count carefully)')}\n"
            "- Make this song UNIQUE and DIFFERENT from others in this session\n"
            "- BANNED words: neon, shimmer, ethereal, celestial, warrior, phoenix, endless, echo\n"
            "- RHYME SCHEME (MANDATORY — makes the song sound natural and musical when sung):\n"
            "  ▸ VERSE: ABAB (lines 1&3 rhyme=A, lines 2&4 rhyme=B). DO NOT write A or B at end of lines!\n"
            "    Example ABAB:\n"
            "      The rain taps slow on the glass tonight\n"
            "      City lights blur soft and fade away\n"
            "      My hoodie warm and the room just right\n"
            "      Nothing left to do but stay\n"
            
            "    ⚠ NEVER write A, B, (A), (B) at end of lyric lines — rhyme silently!\\n"
"  ▸ CHORUS: use AABB pattern — lines 1&2 rhyme, lines 3&4 rhyme\n"
            "    Example AABB:\n"
            "      Just breathe, just stay\n"
            "      Let the moment play\n"
            "      Close your eyes now\n"
            "      Feel the slow glow\n"
            "  ▸ BRIDGE: ABAB or AABB (must be consistent, not random)\n"
            "  ▸ OUTRO: AA couplet or single AB pair (short, closing feel)\n"
            "  RULES:\n"
            "    — End words of rhyming lines MUST share the same vowel/consonant sound\n"
            "    — Never leave a vocal line without a rhyme partner (no orphan lines)\n"
            "    — Near-rhyme is acceptable (night/light, way/stay, soul/whole)\n"
            "    — Keep rhyme natural — do NOT force awkward word order just to rhyme\n"
            "- STRICTLY FORBIDDEN: Do NOT use parentheses () ANYWHERE in lyrics or section labels.\n"
            "  Use ONLY square brackets [] for ALL section tags and instrumental directions.\n"
            "  WRONG: (verse 1), (bridge), (Soft guitar), (instrumental)\n"
            "  CORRECT: [Verse 1], [Bridge], [Soft guitar], [Instrumental]\n"
            "- NEVER use parentheses () in lyrics — Suno reads them as vocals.\n"
            "- ALL section tags MUST use ONLY square brackets []. Example: [Instrumental], [Humming]\n"
            "- ALL instrumental/music directions MUST be written as their OWN line in square brackets.\n"
            "  Write direction as SEPARATE bracketed line after the section tag.\n"
            "  CORRECT: [Instrumental Break]\n[Slide guitar, sparse, slow]\n[Humming]\n"
            "  CORRECT: [Outro]\n[Guitar fading, footsteps in gravel]\n[Silence]\n"
            "  WRONG: [Instrumental Break]\nSlide guitar, sparse, humming  ← NO bare text\n"
            "  WRONG: [Instrumental (soft piano)]  ← NO desc inside brackets\n"
            "  RULE: Any music direction = wrap it in [] on its own line. NEVER leave it as bare text.\n"
            "- BOTH titles: SHORT, CONCRETE, SPECIFIC (2-4 words). NO abstract nouns.\n"
            "  ✅ GOOD: 'Cold Coffee Study', 'Rain on Pavement', 'Last Page of June'\n"
            "  ❌ BAD: 'Eternal Journey', 'Soul Rising', 'Infinite Love'\n\n"
            "SONG STRUCTURE — MANDATORY ORDER:\n"
            f"{_song_structure}\n\n"
            "=== OUTPUT FORMAT (STRICTLY FOLLOW) ===\n"
            "Line 1: TITLE_A: [first concrete title]\n"
            "Line 2: TITLE_B: [second DIFFERENT concrete title]\n"
            "Line 3: STYLE: [COPY the exact user style input — do NOT change, translate, or summarize it]\n"
            "Line 4: LYRICS:\n"
            "Then: full lyrics with section headers\n"
            "NOTHING before TITLE_A, NOTHING after last lyric line.\n\n"
            f"TITLE_A: [unique title version A]\n"
            f"TITLE_B: [unique title version B — MUST differ from A]\n"
            f"STYLE: {detected}\n"
            "LYRICS:\n"
            "[Verse 1]\n"
            "<verse 1 line 1>\n"
            "[Chorus]\n"
            "<chorus line 1>\n"
            "[Verse 2]\n"
            "<verse 2 line 1>\n"
            "[Chorus]\n"
            "<chorus repeat or variation>\n"
            "[Instrumental Break]\n"
            "[<music direction, e.g.: Fingerpicked guitar, slow and sparse>]\n"
            "[Bridge]\n"
            "<bridge line 1>\n"
            "[Final Chorus]\n"
            "<final chorus lines>\n"
            "[Outro]\n"
            "[<music direction, e.g.: Guitar fading, slow footsteps>]\n"
            "[<e.g.: Humming>]\n"
            "[<e.g.: Silence>]\n"
            )
        # ═══════════════════════════════════════════════════════════════════
        raw = await _deepseek_web_generate_lyrics(context, prompt, log_cb, timeout_sec)
        if not raw:
            log_cb(f"[DS-WEB] Lagu {i}: respons kosong - skip.")
            continue
        # ── Smart parse: JSON (custom prompt) atau text (default) ──────────
        _raw_stripped = raw.strip()
        # Bersihkan markdown code block jika ada
        import re as _re
        _raw_clean = _re.sub(r"```(?:json)?", "", _raw_stripped, flags=_re.MULTILINE).strip()
        _raw_clean = _re.sub(r"```", "", _raw_clean).strip()
        # Coba parse JSON dulu (format output custom prompt)
        p = None
        # ── Parser 1: Format PLAIN TEXT (TITLE_A / TITLE_B / LYRICS) ──────────
        import re as _re_js
        _ta_pt = _re_js.search(r'TITLE_A:\s*(.+)', _raw_clean, _re_js.IGNORECASE)
        _tb_pt = _re_js.search(r'TITLE_B:\s*(.+)', _raw_clean, _re_js.IGNORECASE)
        _ly_pt = _re_js.search(r'LYRICS:\s*(.+)', _raw_clean, _re_js.IGNORECASE | _re_js.DOTALL)
        _PLACEHOLDER_SET = {"first creative title", "second creative title", "first title", "second title"}
        if _ta_pt and _ly_pt:
            _ta_v = re.sub(r'["\']+$', '', re.sub(r'^["\']+', '', _ta_pt.group(1).strip()))
            _tb_v = (re.sub(r'["\']+$', '', re.sub(r'^["\']+', '', _tb_pt.group(1).strip())) if _tb_pt else "")
            _ly_v = _ly_pt.group(1).strip()
            if _ta_v.lower() not in _PLACEHOLDER_SET and _ly_v:
                p = {
                    "title":   _ta_v, "title_a": _ta_v,
                    "title_b": _tb_v if _tb_v.lower() not in _PLACEHOLDER_SET else "",
                    "style":   "", "lyrics": _ly_v,
                }
                log_cb(f"[DS-WEB] Plain text parsed OK: '{_ta_v}' / '{_tb_v}'")
        # ── Parser 2: Format JSON (fallback) ──────────────────────────────────
        if p is None:
            _json_candidates = _re_js.findall(r'\{[^{}]*"title_a"[^{}]*\}', _raw_clean, _re_js.DOTALL)
            _PH = {"first title", "second title", "song", "unique title version a", "first creative title"}
            for _jraw in reversed(_json_candidates):
                try:
                    _jdata = json.loads(_jraw)
                    _ta_c = str(_jdata.get("title_a") or "").strip().lower()
                    _ly_c = str(_jdata.get("lyrics") or "").strip()
                    if _ta_c in _PH or not _ly_c:
                        continue
                    p = {
                        "title":   str(_jdata.get("title_a") or f"Song {i}A"),
                        "title_a": str(_jdata.get("title_a") or f"Song {i}A"),
                        "title_b": str(_jdata.get("title_b") or ""),
                        "style":   str(_jdata.get("style") or ""),
                        "lyrics":  str(_jdata.get("lyrics") or ""),
                    }
                    log_cb(f"[DS-WEB] JSON parsed OK: '{p['title_a']}'")
                    break
                except Exception:
                    continue
        if p is None:
            try:
                _jdata = json.loads(_raw_clean)
                _ta_c = str(_jdata.get("title_a") or "").strip().lower()
                _ly_c = str(_jdata.get("lyrics") or "").strip()
                if _ta_c and _ly_c:
                    p = {
                        "title":   str(_jdata.get("title_a") or f"Song {i}A"),
                        "title_a": str(_jdata.get("title_a") or f"Song {i}A"),
                        "title_b": str(_jdata.get("title_b") or ""),
                        "style":   str(_jdata.get("style") or ""),
                        "lyrics":  _ly_c,
                    }
                    log_cb(f"[DS-WEB] JSON full parse OK")
            except Exception as _je:
                log_cb(f"[DS-WEB] JSON parse failed: {_je}")
                p = None
        # ── Parser 3: text parser generic ─────────────────────────────────────
        if p is None:
            p = _parse_deepseek_response(raw)
        # Sanitize: kurung () → braket [] agar tidak dibaca Suno sebagai vokal
        if p.get("lyrics"):
            p["lyrics"] = _sanitize_lyrics(p["lyrics"])
        title_a = p.get("title_a") or p.get("title") or f"Song {i}A"
        title_b = p.get("title_b") or ""
        if not title_b:
            _w = title_a.split()
            title_b = _generate_title_b(title_a, i)
        # Style = PERSIS input user, BUKAN dari DeepSeek response
        style  = description.strip().rstrip(".,").strip()
        lyrics = "" if instrumental else p.get("lyrics", "")
        # FIX: cek lofi HANYA dari style (bukan description)
        _sl_w = style.lower() if style else ""
        _is_lofi_w = any(kw in _sl_w for kw in [
            "lofi","lo-fi","lo fi","chillhop","study beats",
            "campursari","campur sari","langgam jawa","langgam","gamelan","sinden","karawitan"
        ])
        _is_custom_now = bool(get_active_prompt())
        _min_w = 0 if _is_mini else (100 if _is_custom_now else (200 if _is_lofi_w else MIN_LYRICS_CHARS))
        if not instrumental and _min_w > 0 and len(lyrics) < _min_w:
            log_cb(f"[DS-WEB] Lagu {i}: lirik {len(lyrics)} char < {_min_w} — terlalu pendek, tetap dipakai.")
        log_cb(f"[DS-WEB] OK '{title_a}' / '{title_b}' | {len(lyrics)} char | style: {style[:60]}")
        songs.append({
            "title": title_a, "title_a": title_a, "title_b": title_b,
            "style": style, "lyrics": lyrics,
            "instrumental": instrumental,
            "profile_name": config.get("profile_name", ""),
            "lyric_source": _lyric_source,  # FIX v5.40.1: mini skip check needs this
        })
        if i < quantity:
            await asyncio.sleep(3)
    log_cb(f"[DS-WEB] {len(songs)}/{quantity} lagu siap dimasukkan ke Suno.")
    return songs


def is_claude_provider(cfg: dict) -> bool:
    base = cfg.get("base_url", "").lower()
    return "anthropic" in base or "api.claude" in base


def call_ai(messages: list, cfg: dict, max_tokens: int = 1800, temperature: float = 0.9) -> str:
    if is_claude_provider(cfg):
        return _call_claude(messages, cfg, max_tokens, temperature)
    return _call_openai_compat(messages, cfg, max_tokens, temperature)


def _call_openai_compat(messages, cfg, max_tokens, temperature) -> str:
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {"model": cfg["model"], "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    # FIX#6b: robust parser — handle berbagai format response OpenRouter
    if "choices" in result and result["choices"]:
        choice = result["choices"][0]
        if "message" in choice and "content" in choice["message"]:
            return choice["message"]["content"].strip()
        if "text" in choice:
            return choice["text"].strip()
    if "content" in result:
        c = result["content"]
        if isinstance(c, list) and c:
            return c[0].get("text", "").strip()
        if isinstance(c, str):
            return c.strip()
    if "message" in result:
        return str(result["message"]).strip()
    raise KeyError(f"Tidak bisa parse response: {str(result)[:200]}")


def _call_claude(messages, cfg, max_tokens, temperature) -> str:
    system_text = ""
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        else:
            user_messages.append(m)
    url = cfg["base_url"].rstrip("/") + "/messages"
    payload = {"model": cfg["model"], "max_tokens": max_tokens,
                "temperature": temperature, "messages": user_messages}
    if system_text:
        payload["system"] = system_text
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "x-api-key": cfg["api_key"],
        "anthropic-version": "2023-06-01",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["content"][0]["text"].strip()


def detect_language(text: str) -> str:
    id_markers = [
        "lagu", "tentang", "cinta", "sedih", "gembira", "nuansa", "melankolis",
        "untuk", "dengan", "yang", "dan", "di", "ke", "dari", "sangat", "adalah",
        "rindu", "bahagia", "kau", "aku", "kamu", "bisa", "ingin", "hidup",
        "malam", "pagi", "siang", "hari", "waktu", "perjalanan", "mimpi",
    ]
    words = text.lower().split()
    count = sum(1 for w in words if w in id_markers)
    return "id" if count >= 2 else "en"


def generate_style_ai(description: str, cfg: dict) -> str:
    lang = detect_language(description)
    lang_note = " The description is in Indonesian but output style tags in English." if lang == "id" else ""
    messages = [
        {"role": "system", "content": (
            "You are a Suno AI music style tag generator. "
            "Your ONLY job: output comma-separated style tags. "
            "RULES: "
            "1. Output ONLY tags separated by commas. Zero sentences. Zero explanations. "
            "2. Keep the exact genre the user specified. "
            "3. Add BPM, vocal style, production details as extra tags. "
            "CORRECT example output: female vocal, R&B, warm electric piano, 75 BPM, soulful, lush reverb, breathy vocals "
            "WRONG example output: Here are the style tags: female vocal... (this is wrong, do not write intro sentences)"
        )},
        {"role": "user", "content": (
            f"Input: {description}.{lang_note} "
            "Output tags only:"
        )},
    ]
    raw = call_ai(messages, cfg, max_tokens=250, temperature=0.3)
    return _clean_style_tags(raw, description)


def _clean_style_tags(raw: str, fallback: str) -> str:
    """Strip verbose model output — ambil hanya comma-separated style tags."""
    import re as _re
    # Hapus markdown/code block
    raw = _re.sub(r"```[\s\S]*?```", "", raw)
    raw = _re.sub(r"[*_`#]", "", raw)
    # Hapus intro kalimat seperti "Here are the tags:", "Output:", "Sure,", dll
    raw = _re.sub(
        r"(?i)^(here are[^:]*:|output[^:]*:|sure[,!.]?|of course[,!.]?|"
        r"certainly[,!.]?|here[' ]?s[^:]*:|the (style )?tags[^:]*:|"
        r"based on[^:]*:|note[^:]*:|we need[^.]+\.?)",
        "", raw.strip()
    )
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines:
        return fallback
    # Ambil baris dengan koma terbanyak (= paling mirip tag list)
    best = max(lines, key=lambda l: l.count(","))
    # Kalau koma < 2, coba gabung semua lalu filter per segmen
    if best.count(",") < 2:
        all_text = " ".join(lines)
        parts = [p.strip() for p in all_text.split(",")]
        skip_starts = ("we ", "i ", "the output", "note:", "output:", "here ",
                       "this ", "these ", "please ", "sure", "of course",
                       "certainly", "absolutely", "based")
        tags = [p for p in parts
                if p and len(p) < 55
                and not any(p.lower().startswith(s) for s in skip_starts)]
        if len(tags) >= 3:
            best = ", ".join(tags)
    # Bersihkan sisa tanda kutip & whitespace
    best = _re.sub(r'["\'\']', "", best).strip().strip(",").strip()
    return best if best else fallback


def generate_song_ai(description: str, style: str, song_index: int,
                     total: int, cfg: dict, instrumental: bool = False,
                     language: str = "") -> dict:
    # ══ Custom Prompt Mode ════════════════════════════════════════════════════
    _active_p = get_active_prompt()
    if _active_p and _active_p.get("template", "").strip():
        import sys as _sys
        print(f"[CUSTOM PROMPT] Menggunakan: '{_active_p.get('label','Custom')}' untuk lagu {song_index}/{total}", flush=True)
        _csys  = _active_p.get("system", "").strip()
        _ctpl  = _active_p["template"]
        _cuser = _safe_prompt_format(
            _ctpl,
            description=description,
            style=style,
            index=song_index,
            total=total,
        )
        _msgs = []
        if _csys:
            _msgs.append({"role": "system", "content": _csys})
        _msgs.append({"role": "user", "content": _cuser})
        _raw = call_ai(_msgs, cfg, max_tokens=1800, temperature=0.95)
        # Bersihkan markdown code block
        _raw = re.sub(r"```(?:json)?", "", _raw, flags=re.MULTILINE).strip()
        _raw = re.sub(r"```", "", _raw).strip()
        try:
            _pc  = json.loads(_raw)
            _ta  = str(_pc.get("title_a", _pc.get("title", f"Song {song_index}A"))).strip()
            _tb  = str(_pc.get("title_b", f"Song {song_index}B")).strip()
            _ly  = str(_pc.get("lyrics", "")).strip()
        except Exception:
            _ls  = [l for l in _raw.splitlines() if l.strip()]
            _ta  = _ls[0][:60] if _ls else f"Song {song_index}"
            _tb  = _ta + " II"
            _ly  = "\n".join(_ls[1:]) if len(_ls) > 1 else _raw
        _ly = sanitize_lyrics(_ly) if _ly else _ly
        return {"title": _ta, "title_a": _ta, "title_b": _tb, "lyrics": _ly}
    # ════════════════════════════════════════════════════════════════════════
    if language:
        lang_instr = f"Write the title and ALL lyrics STRICTLY in {language}. Section tags stay in English."
    else:
        lang = detect_language(description)
        lang_instr = ("Write the title and lyrics in Indonesian (Bahasa Indonesia)."
                      if lang == "id" else "Write the title and lyrics in English.")
    if instrumental:
        lyrics_instr = (
            "THIS IS AN INSTRUMENTAL TRACK — no sung lyrics at all. "
            "Set the JSON field 'lyrics' to an EMPTY STRING. "
            "Still provide two creative, specific titles (title_a and title_b) "
            "that reflect the mood/genre. Avoid generic words: Instrumental, Music, Theme, Beat."
        )
    else:
        _sl = style.lower()
        # Load genre mapping dari genres.json (eksternal, bisa diedit user)
        _genre_db  = load_genres()
        _genre_guide = ""
        for _gname, _gdata in _genre_db.items():
            if any(kw in _sl for kw in _gdata.get("keywords", [])):
                _genre_guide = _gdata.get("guide", "")
                break
        if not _genre_guide:
            _genre_guide = (
                f"The music style is: {style}. "
                "Write lyrics that PERFECTLY match the mood, energy, "
                "and cultural themes of this genre."
            )

        lyrics_instr = (
            f"This is song #{song_index} of {total} songs in this session.\n"
            f"MANDATORY GENRE DIRECTIVE: {_genre_guide}\n\n"
            "Make this version UNIQUE and DIFFERENT from other songs. "
            "Use different metaphors, imagery, story angle, and word choices. "
            "STRICTLY AVOID these overused/cliche words in lyrics: "
            "neon, twilight, shimmer, glimmer, glow, echo, whisper, fade, drift, "
            "cascade, illuminate, ethereal, celestial, infinite, endless, forever, "
            "dance in the rain, burning flame, phoenix, warrior, unbreakable. "
            "Use concrete, specific, fresh and original imagery instead. "
            "SONG STRUCTURE — MANDATORY ORDER:\n"            "  [Verse 1]\n"            "  [Pre-Chorus] (optional)\n"            "  [Chorus]\n"            "  [Verse 2]\n"            "  [Pre-Chorus] (optional)\n"            "  [Chorus]\n"            "  [Instrumental Break]  ← AFTER 2nd Chorus ONLY, NEVER at the start\n"            "  [Bridge]\n"            "  [Final Chorus]\n"            "  [Outro]\n"            "RULE: NEVER start with [Intro] or [Instrumental]. [Instrumental Break] = empty line, no lyrics. "
            "Minimum 20 lines of actual lyrics (not counting section headers). "
            f"Minimum {MIN_LYRICS_CHARS} characters total."
        )
    _TITLE_THEMES = [
        "2am fridge light in an empty kitchen", "Tuesday rain on a bus window",
        "the smell of old books in a thrift store", "shoes left by the door after a long shift",
        "a half-drunk cup of coffee gone cold", "voicemail you never deleted",
        "the last train home on a Friday night", "waiting room with a broken clock",
        "a conversation left unfinished for years", "the moment before you say goodbye",
        "deciding to stay when you wanted to leave", "realising you have outgrown someone",
        "the first morning after everything changed", "finding an old photo you forgot existed",
        "saying sorry too late", "choosing yourself for the first time",
        "a bar closing its doors at 3am", "sunrise seen from an overnight flight",
        "small-town Sunday with nowhere to go", "the last house on a dead-end street",
        "a convenience store at midnight", "swimming pool in winter empty and quiet",
        "backseat of a car parked outside your childhood home",
        "hotel room the night before something big",
        "love that arrived at the wrong time", "growing apart without noticing",
        "the version of me you never got to meet", "two people reading the same sky differently",
        "missing someone who is still alive", "the space between holding on and letting go",
        "what we never said out loud", "falling for someone who is already leaving",
        "the gap between who I am and who I pretend to be",
        "carrying something heavy and pretending it is fine",
        "quietly rebuilding after a year of survival",
        "the particular loneliness of being understood by no one",
        "small victories that no one celebrates with you",
        "the relief of finally admitting you are tired",
        "peace that comes after you stop fighting yourself",
        "relearning joy after a season of grief",
        "a year that aged you more than expected", "nostalgia for a time that never existed",
        "the way certain songs trap a whole year inside them",
        "remembering someone by the music they loved",
        "the decade that passed while you were not paying attention",
        "a childhood summer you can almost smell but not quite see",
        "the first step after standing still for too long",
        "planting something knowing you will not see it bloom",
        "light at the edge of a very long tunnel",
        "choosing to start again with nothing but the will to try",
        "the quiet courage of ordinary people on ordinary days",
    ]
    import hashlib as _hl
    _seed_str = f"{description[:40]}{style[:20]}{song_index}"
    _seed_int  = int(_hl.md5(_seed_str.encode()).hexdigest(), 16)
    title_hint = _TITLE_THEMES[_seed_int % len(_TITLE_THEMES)]

    messages = [
        {"role": "system", "content": (
            "You are a professional award-winning songwriter. "
            "You write emotionally resonant, commercially viable, original song lyrics. "
            "CRITICAL RULE: Every song MUST have a 100% UNIQUE title — "
            "NEVER repeat the same opening word or concept as any other song. "
            "Forbidden first words for titles: Quiet, Silent, Echo, Light, Shadow, "
            "Dream, Heart, Soul, Whisper, Broken, Gentle, Soft. "
            "You always respond in valid JSON format."
        )},
        {"role": "user", "content": (
            f"Write song #{song_index} of {total}. "
            f"This song's unique theme angle: '{title_hint}'.\n"
            f"Base description: \"{description}\"\n\n"
            f"Music style: {style}\n\n{lyrics_instr}\n\n{lang_instr}\n\n"
            f"IMPORTANT: Generate TWO different song titles for this song's TWO versions, "
            f"both reflecting the angle: '{title_hint}'.\n"
            "TITLE RULES (strictly enforced for BOTH titles):\n"
            "  - 2 to 5 words ONLY. No subtitles, no colons, no punctuation.\n"
            "  - CONCRETE and SPECIFIC — NO abstract words: "
            "Love, Light, Soul, Dream, Echo, Shadow, Fire, Rain, Heart, Whisper, "
            "Broken, Quiet, Silent, Gentle, Eternal, Infinite, Forever, Beautiful, Perfect.\n"
            "  - title_a and title_b must be DIFFERENT from each other.\n"
            "  - GOOD: 'Tuesday in the Rain', '3AM Fridge Hum', 'Shoes By The Door'.\n"
            "  - BAD: 'Endless Love', 'Broken Heart', 'Silent Night'.\n"
            "Respond in this exact JSON format (no markdown, no code block):\n"
            '{"title_a": "First Title", "title_b": "Second Title", "lyrics": "[Verse 1]\\nLine 1\\n..."}'
        )},
    ]
    raw = call_ai(messages, cfg, max_tokens=1800, temperature=0.97)
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```\s*$", "", raw, flags=re.MULTILINE).strip()
    try:
        parsed  = json.loads(raw)
        title_a = str(parsed.get("title_a", parsed.get("title", f"Song {song_index}A"))).strip()
        title_b = str(parsed.get("title_b", f"Song {song_index}B")).strip()
        lyrics  = str(parsed.get("lyrics", "")).strip()
    except json.JSONDecodeError:
        ta_m = re.search(r'"title_a"\s*:\s*"([^"]+)"', raw)
        tb_m = re.search(r'"title_b"\s*:\s*"([^"]+)"', raw)
        t_m  = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
        lm   = re.search(r'"lyrics"\s*:\s*"([\s\S]+?)"(?:\s*}?\s*$)', raw)
        title_a = (ta_m or t_m).group(1) if (ta_m or t_m) else f"Song {song_index}A"
        title_b = tb_m.group(1) if tb_m else f"Song {song_index}B"
        lyrics  = lm.group(1).replace("\\n","\n") if lm else ""
    _bad = {"Song Title Here","First Title","Second Title","First Title Here","Second Title Here",
            "Title","Song title","[Title]",""}
    if title_a in _bad and title_b in _bad and not lyrics:
        raise ValueError(f"Model returned placeholder (title_a={title_a!r})")
    if not lyrics and not instrumental:
        raise ValueError(f"Model returned empty lyrics (title_a={title_a!r})")
    # FIX: lofi/semi-instrumental boleh lirik pendek (min 400 char)
    # FIX: cek lofi HANYA dari style bukan description
    _sl_check = style.lower() if style else ""
    _is_lofi_check = any(kw in _sl_check for kw in [
        "lofi", "lo-fi", "lo fi", "chillhop", "chill hop", "study beats", "chill beats"
    ])
    _min_chars = 200 if _is_lofi_check else MIN_LYRICS_CHARS
    if not instrumental and len(lyrics) < _min_chars:
        raise ValueError(
            f"Lirik terlalu pendek: {len(lyrics)} karakter (minimum {_min_chars}). "
            f"Retry untuk mendapatkan lirik lebih lengkap."
        )
    def _fix_t(t, sfx):
        if t in _bad or not t.strip():
            words = lyrics.replace("\n"," ").replace("[Verse 1]","").replace("[Chorus]","").split()
            return " ".join(w for w in words[:5] if not w.startswith("[")).title() or f"Song {song_index}{sfx}"
        return t
    title_a = _fix_t(title_a, "A")
    title_b = _fix_t(title_b, "B")
    # Sanitize kurung () → braket [] sebelum dikirim ke Suno
    lyrics = _sanitize_lyrics(lyrics) if lyrics else lyrics
    return {"title_a": title_a, "title_b": title_b, "lyrics": lyrics}


# ------------------------------------------------------------------
# Prepare songs: AI or fallback
# ------------------------------------------------------------------

def prepare_songs_with_ai(config: dict, log_cb) -> list:
    description  = config["description"]
    quantity     = config.get("quantity", 1)
    instrumental = config.get("instrumental", False)
    _lang_cfg    = (config.get("language", "") or "").strip()
    ai_cfg = load_ai_config()
    use_ai = bool(ai_cfg.get("api_key", "").strip())

    if use_ai:
        base_url = ai_cfg.get("base_url", "").strip()
        is_openrouter = "openrouter.ai" in base_url

        if is_openrouter:
            models_to_try = list(OPENROUTER_FREE_MODELS)
            current_model = ai_cfg.get("model", "").strip()
            if current_model and current_model in models_to_try:
                models_to_try.remove(current_model)
            if current_model:
                models_to_try.insert(0, current_model)

            # FIX: kumpulkan semua API keys untuk rotasi otomatis
            api_keys = [k.strip() for k in ai_cfg.get("api_keys", []) if k.strip()]
            if not api_keys:
                single = ai_cfg.get("api_key", "").strip()
                if single:
                    api_keys = [single]

            if not api_keys:
                log_cb("[AI] Tidak ada API key — fallback ke built-in generator.")
            else:
                total_combos = len(models_to_try) * len(api_keys)
                attempt = 0
                _ai_result = None
                success = False

                for model in models_to_try:
                    if success or _stop_requested.is_set():
                        break
                    if not model:
                        continue
                    for key_idx, key in enumerate(api_keys):
                        if success or _stop_requested.is_set():
                            break
                        attempt += 1
                        cfg_try = dict(ai_cfg)
                        cfg_try["model"]   = model
                        cfg_try["api_key"] = key
                        kl = (f"key#{key_idx+1}({key[:8]}...)"
                              if len(key) > 8 else f"key#{key_idx+1}")
                        log_cb(f"[AI] [{attempt}/{total_combos}] {model} | {kl}")
                        try:
                            _ai_result = _prepare_ai(description, quantity, instrumental,
                                                     cfg_try, log_cb, language=_lang_cfg)
                            log_cb(f"[AI] ✓ Berhasil: {model} | {kl}")
                            success = True
                            break
                        except urllib.error.HTTPError as e:
                            body = e.read().decode("utf-8", errors="replace")[:150]
                            log_cb(f"[AI] ✗ HTTP {e.code}: {body[:100]}")
                            if e.code == 429:
                                log_cb(f"[AI] Rate limit {kl} → coba key berikutnya...")
                                import time as _t; _t.sleep(3)
                            elif e.code in (401, 403):
                                log_cb(f"[AI] Auth error {kl} → skip key ini.")
                            elif e.code == 404:
                                log_cb("[AI] Model tidak tersedia → skip model ini.")
                                break
                            elif e.code == 503:
                                log_cb("[AI] Server overload → tunggu 8s...")
                                import time as _t; _t.sleep(8)
                            else:
                                log_cb("[AI] Coba berikutnya...")
                        except Exception as e:
                            log_cb(f"[AI] ✗ {str(e)[:120]}")

                if success and _ai_result is not None:
                    return _ai_result

                log_cb("[AI] Semua kombinasi gagal — tunggu 10s lalu final retry...")
                import time as _t; _t.sleep(10)
                try:
                    cfg_retry = dict(ai_cfg)
                    cfg_retry["model"]   = models_to_try[0]
                    cfg_retry["api_key"] = api_keys[0]
                    log_cb(f"[AI] Final retry: {models_to_try[0]} | key#1")
                    _ai_result = _prepare_ai(description, quantity, instrumental, cfg_retry, log_cb, language=_lang_cfg)
                    log_cb("[AI] ✓ Berhasil di final retry!")
                    return _ai_result
                except Exception:
                    pass
                log_cb("[AI] Semua key & model OpenRouter gagal → fallback built-in generator.")
        else:
            log_cb(f"[AI] Model: {ai_cfg['model']} | {ai_cfg['base_url']}")
            try:
                return _prepare_ai(description, quantity, instrumental, ai_cfg, log_cb, language=_lang_cfg)
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:300]
                log_cb(f"[AI] HTTP Error {e.code}: {body}")
                log_cb("[AI] Fallback ke built-in generator...")
            except Exception as e:
                log_cb(f"[AI] Error: {e}")
                log_cb("[AI] Fallback ke built-in generator...")
    else:
        log_cb("[GEN] AI tidak dikonfigurasi. Klik 'AI Settings' untuk setup.")
    return _prepare_fallback(description, quantity, instrumental, log_cb)


def _prepare_ai(description, quantity, instrumental, ai_cfg, log_cb,
                language: str = "") -> list:
    # Style = PERSIS input user, tidak dimodifikasi AI sama sekali
    style = description.strip().rstrip(".,").strip()
    log_cb(f"  Style BAKU (dari input user, tidak diubah AI): {style}")

    # Siapkan fallback lyrics bank — style TETAP dari AI, bukan deteksi ulang genre
    _fb_genre, _ = _fallback_detect_genre(description)
    _fb_bank = _FALLBACK_LYRICS.get(_fb_genre, _FALLBACK_LYRICS["default"])

    songs = []
    for i in range(1, quantity + 1):
        if _stop_requested.is_set():
            break
        log_cb(f"[AI] Generating song {i}/{quantity}...")
        try:
            result = generate_song_ai(description, style, i, quantity, ai_cfg, instrumental, language=language)
            # FIX: handle title_a/title_b (custom prompt) dan title (default)
            _title = result.get("title") or result.get("title_a") or f"Song {i}"
            songs.append({
                "title": _title, "style": style,
                "lyrics": result["lyrics"], "instrumental": instrumental,
            })
            log_cb(f"  Lagu {i}: '{_title}' | {len(result['lyrics'].splitlines())} baris")
        except Exception as e:
            # Fallback PER-LAGU: tetap pakai style yang sudah digenerate, BUKAN deteksi ulang
            log_cb(f"  [AI] Error lagu {i}: {e}")
            log_cb(f"  [FALLBACK] Built-in lyrics, style TETAP: {style[:55]}...")
            lyrics = _fb_bank[(i - 1) % len(_fb_bank)] if not instrumental else ""
            words  = description.strip().rstrip(".,!?").split()
            base   = " ".join(words[:4]).title()
            title  = base if i == 1 else f"{base} Vol.{i}"
            songs.append({
                "title":       title,
                "style":       style,     # <-- PENTING: style R&B/genre user tetap dipakai
                "lyrics":      lyrics,
                "instrumental": instrumental,
            })
            log_cb(f"  Lagu {i}: '{title}' (fallback lyrics, style genre user tetap dipertahankan)")
    return songs


# ------------------------------------------------------------------
# Fallback built-in generator
# ------------------------------------------------------------------

_FALLBACK_LYRICS = {
    "hiphop": [
        "[Verse 1]\nStarted with nothing but a dream in my chest\nStayed up every night just to give my best\nThey said impossible, I proved them wrong\nEvery single setback just made me more strong\n\n[Chorus]\nOn top, can't stop\nLevel up, won't drop\nEverything I built I built from the bottom up\nAll my people know we hot\n\n[Bridge]\nThis is more than money, more than fame\nEvery sacrifice that led me to this lane\n\n[Outro]\nWe on, can't stop us now",
        "[Verse 1]\nWoke up with a mission, wrote it down and got busy\nThe doubters got loud but my focus stayed different\nI move in silence let the work do the talking\nWhile they sleeping I'm out here relentlessly walking\n\n[Chorus]\nI didn't come this far to only come this far\nBreaking through the ceiling reaching for the stars\nEvery scar a medal every setback a test\nGone through the worst so I deserve the best\n\n[Bridge]\nNo days off, the grind don't stop\n\n[Outro]\nBuilt this from the ground up, watch me now",
        "[Verse 1]\nThey counted me out said I'd never make it\nLooked in my eyes said boy you'll never take it\nSo I took that pain and turned it into fuel\nNow I'm living proof you can rewrite the rules\n\n[Chorus]\nDifferent breed, different speed\nI don't follow I just lead\nGrinding daily, turning water into bread\n\n[Bridge]\nMindset of a champion, never settle for less\n\n[Outro]\nWatch me work",
        "[Verse 1]\nCame from the bottom now everybody notice\nUsed to be invisible now I'm the focus\nEvery early morning every sacrifice\nEvery single time I had to think twice\n\n[Chorus]\nThis ain't luck this is work\nThis ain't given this is earned\nNow standing in the fire and I don't burn\n\n[Bridge]\nLegacy is what I'm building brick by brick\n\n[Outro]\nLegacy, that's all I'm chasing",
        "[Verse 1]\nI remember when I had to count my change\nBut I had a vision and a burning desire\nTo take my life and set my future on fire\n\n[Chorus]\nFrom the bottom to the top watch me rise\nSuccess is my revenge, best surprise\nDifferent path different pace different shine\n\n[Bridge]\nNever let them dim your light, ever\n\n[Outro]\nThis is just the beginning",
    ],
    "default": [
        "[Verse 1]\nI woke up this morning with something to say\nA feeling inside me that just won't go away\nLike a fire that's burning, a light in the dark\nIt started quietly but now fills my heart\n\n[Pre-Chorus]\nI don't want to keep this to myself anymore\nThis is everything I've been waiting for\n\n[Chorus]\nWe're alive and we're burning bright\nDancing through the day into the night\nNothing gonna stop us, nothing feels too far\nWe are everything we are\n\n[Bridge]\nThis is our time, this is our song\nWe've been waiting for this moment all along\n\n[Outro]\nBurning bright tonight",
        "[Verse 1]\nYou and I on a Tuesday afternoon\nNothing planned but somehow everything in tune\nIce cream and the radio and nowhere to be\nThis is all I ever wanted, you and me\n\n[Chorus]\nNothing fancy, nothing complicated\nJust the simple things that left me satiated\nMore than everything and also just enough\n\n[Bridge]\nDon't need the world just need this afternoon with you\n\n[Outro]\nJust enough, more than enough",
        "[Verse 1]\nEverybody's running to be somewhere else\nBut I found my something in the smallest things\nIn the ordinary gold that every Tuesday brings\n\n[Chorus]\nThis is the golden age, don't let it go\nLook around at everything you almost missed\nIt's all right here on the most ordinary list\n\n[Bridge]\nThe golden age is now, right here\n\n[Outro]\nRight here, right now, golden",
        "[Verse 1]\nThree words you said at two in the afternoon\nSomething small that turned into my favourite tune\nWith one small moment turning into something clear\n\n[Chorus]\nIt's the little things that build the biggest life\nBut the Tuesday texts and the stupid jokes we share\nThe proof that someone always cares\n\n[Bridge]\nSmall moments make a life worth living\n\n[Outro]\nLittle things, the most important things",
        "[Verse 1]\nStarted from a spark now it's a symphony\nEverything I hoped for now reality\nNever knew that good could feel like this\n\n[Chorus]\nLook how far we've come look how far we go\nFrom the seed to flower from the ember to the glow\nAnd now it's bloom, and now it's mine\n\n[Bridge]\nGrowth is not always visible but it's always real\n\n[Outro]\nLook how far, look how far we've come",
    ],
}


def _fallback_detect_genre(description: str) -> tuple:
    d = description.lower()
    happy    = any(w in d for w in ["happy","fun","joy","party","seru","senang","gembira","pesta","bahagia"])
    sad      = any(w in d for w in ["sad","cry","heartbreak","miss","lonely","sedih","rindu","patah","kehilangan","nangis"])
    romantic = any(w in d for w in ["love","romance","crush","cinta","sayang","together","sweetheart"])
    hype     = any(w in d for w in ["hype","energy","power","strong","fire","semangat","bangkit","perjuangan","fight"])
    hustle   = any(w in d for w in ["hustle","grind","work","success","kerja","sukses","uang","money","rich","boss"])
    party    = any(w in d for w in ["dance","dancefloor","club","weekend","dansa","clubbing","disco"])
    if hype and hustle: return "hiphop", "hip hop, trap, 808 bass, confident flow, motivational, 140bpm, studio quality"
    if party and happy: return "edm",    "EDM, progressive house, euphoric drop, festival anthem, 128bpm, dancefloor"
    if romantic and sad: return "rnb",   "R&B soul, emotional ballad, piano, warm vocals, cinematic strings, 85bpm"
    if romantic:         return "rnb",   "R&B soul, smooth production, warm vocals, lush arrangement, 90bpm"
    if sad:              return "indie", "indie pop, melancholic, piano-driven, emotional vocals, lo-fi warmth, 80bpm"
    if party:            return "edm",   "EDM, upbeat house, fun synths, danceable, 128bpm"
    if hype:             return "rock",  "pop rock, anthemic, electric guitar, punchy drums, 135bpm"
    if happy:            return "pop",   "pop, catchy hooks, upbeat, bright synths, sing-along chorus, 120bpm"
    return "pop", "modern pop, emotional, catchy chorus, professional production, 110bpm"


def _prepare_fallback(description, quantity, instrumental, log_cb) -> list:
    genre, _detected_style = _fallback_detect_genre(description)
    # Style = persis input user, tidak diganti deteksi otomatis
    style = description.strip().rstrip(".,").strip()
    log_cb(f"[GEN] Genre detected: {genre} | Style BAKU: {style[:60]}...")
    log_cb(f"[GEN] Style SAMA (dari input user) untuk semua {quantity} lagu.")
    bank = _FALLBACK_LYRICS.get(genre, _FALLBACK_LYRICS["default"])
    songs = []
    for i in range(quantity):
        if _stop_requested.is_set():
            break
        lyrics = bank[i % len(bank)] if not instrumental else ""
        words = description.strip().rstrip(".,!?").split()
        base_title = " ".join(words[:4]).title()
        suffixes = ["", " (Ver. 2)", " (Ver. 3)", " (Ver. 4)", " (Ver. 5)"]
        title = base_title + (suffixes[i] if i < len(suffixes) else f" (Ver. {i+1})")
        songs.append({"title": title, "style": style, "lyrics": lyrics, "instrumental": instrumental})
        log_cb(f"  Lagu {i+1}: '{title}'")
    return songs


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def ensure_dirs():
    APP_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text("[]", encoding="utf-8")


def _get_profile_abs(profile_dir: str) -> str:
    """Resolve profile_dir ke absolute path berdasarkan DATA_DIR saat ini.
    Support:
    - Slug/nama folder saja  -> DATA_DIR / slug
    - Path absolut valid     -> dipakai langsung
    - Path absolut lama mati -> migrate ke DATA_DIR / slug
    """
    if not profile_dir:
        return str(DATA_DIR / "unknown")
    p = Path(profile_dir)
    if not p.is_absolute():
        return str(DATA_DIR / p.name)
    if p.exists():
        return str(p)
    # Path absolut tidak valid (folder dipindah) → pakai slug di DATA_DIR sekarang
    return str(DATA_DIR / p.name)


def resolve_profile_dir(profile_dir: str) -> str:
    """Alias publik untuk _get_profile_abs."""
    return _get_profile_abs(profile_dir)


def load_profiles():
    ensure_dirs()
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    changed = False
    for p in raw:
        if "profile_dir" in p:
            original = p["profile_dir"]
            abs_path = _get_profile_abs(original)
            slug = Path(abs_path).name
            # Simpan slug saja (portable), tambah _abs untuk runtime
            if original != slug:
                p["profile_dir"] = slug
                changed = True
            p["_profile_dir_abs"] = abs_path  # runtime only, tidak disimpan
    if changed:
        _save_profiles_raw(raw)
    return raw


def _save_profiles_raw(profiles):
    """Internal save tanpa strip _profile_dir_abs (dipakai saat migrate)."""
    clean = []
    for p in profiles:
        pc = {k: v for k, v in p.items() if not k.startswith("_")}
        if "profile_dir" in pc:
            pc["profile_dir"] = Path(pc["profile_dir"]).name  # selalu simpan slug
        clean.append(pc)
    CONFIG_FILE.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")


def save_profiles(profiles):
    """Simpan profiles — profile_dir disimpan sebagai slug relatif agar portable."""
    _save_profiles_raw(profiles)


def _minimize_chrome_windows():
    """Minimize semua window Chrome menggunakan Windows API (ctypes)."""
    try:
        import ctypes
        import ctypes.wintypes

        SW_MINIMIZE = 6
        EnumWindows       = ctypes.windll.user32.EnumWindows
        GetWindowText     = ctypes.windll.user32.GetWindowTextW
        IsWindowVisible   = ctypes.windll.user32.IsWindowVisible
        ShowWindow        = ctypes.windll.user32.ShowWindow
        WNDENUMPROC       = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def enum_cb(hwnd, _):
            if IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                GetWindowText(hwnd, buf, 256)
                title = buf.value.lower()
                # Minimize window yang title-nya mengandung indikator Chrome
                if "chrome" in title or "chromium" in title or "suno" in title:
                    ShowWindow(hwnd, SW_MINIMIZE)
            return True

        EnumWindows(WNDENUMPROC(enum_cb), 0)
    except Exception:
        pass  # Tidak fatal jika gagal (non-Windows atau permission issue)


def find_chrome():
    """Cari Chrome di path default + registry Windows + path dari app_config."""
    # 1. Cek dari app_config dulu (user sudah pernah set)
    try:
        cfg = load_app_config()
        saved = cfg.get("chrome_path", "")
        if saved and os.path.exists(saved):
            return saved
    except Exception:
        pass

    # 2. Cek DEFAULT_CHROME_PATHS
    for cp in DEFAULT_CHROME_PATHS:
        if os.path.exists(cp):
            return cp

    # 3. Cari via Windows Registry
    try:
        import winreg
        for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (
                r"SOFTWARE\Google\Chrome\BLBeacon",
                r"SOFTWARE\Wow6432Node\Google\Chrome\BLBeacon",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            ):
                try:
                    with winreg.OpenKey(root_key, sub) as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val and os.path.exists(val):
                            return val
                except Exception:
                    continue
    except Exception:
        pass

    # 4. Cari via PATH environment
    try:
        import shutil as _sh
        found = _sh.which("chrome") or _sh.which("google-chrome") or _sh.which("chromium")
        if found and os.path.exists(found):
            return found
    except Exception:
        pass

    # 5. Scan folder umum tambahan
    extra_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
        # Portable Chrome di drive lain
        r"D:\Chrome\chrome.exe",
        r"E:\Chrome\chrome.exe",
        r"F:\Chrome\chrome.exe",
    ]
    for cp in extra_paths:
        if cp and os.path.exists(cp):
            return cp

    return None


def _prompt_to_folder_name(description: str, max_len: int = 40) -> str:
    """
    Konversi description/style prompt ke nama folder yang aman.
    Dipotong maks max_len karakter. Contoh:
      'rnb female vocal healing 75bpm' → 'rnb_female_vocal_healing_75bpm'
      'pop melankolis female vocal piano strings 85bpm cinematic sad' → 'pop_melankolis_female_vocal_piano_str'
    """
    import re as _re
    # Bersihkan karakter tidak aman
    safe = _re.sub(r'[^a-zA-Z0-9\s_-]', '', description.strip())
    # Ganti spasi/koma/titik dengan underscore
    safe = _re.sub(r'[\s,./]+', '_', safe)
    # Hapus underscore ganda
    safe = _re.sub(r'_+', '_', safe).strip('_')
    # Potong ke max_len
    if len(safe) > max_len:
        safe = safe[:max_len].rstrip('_')
    return safe.lower() or "suno_songs"


def slugify(text: str) -> str:
    keep = []
    for ch in text.strip():
        if ch.isalnum():
            keep.append(ch.lower())
        elif ch in (" ", "-", "_"):
            keep.append("_")
    slug = "".join(keep).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "account"


def make_safe_filename(title: str) -> str:
    invalid = r'\/:*?"<>|'
    safe = title.strip()
    for ch in invalid:
        safe = safe.replace(ch, "")
    return safe[:100].strip() or "song"


def get_today():
    return date.today().isoformat()


def get_create_count(prof: dict) -> int:
    today = get_today()
    if prof.get("counter_date") != today:
        prof["counter_date"] = today
        prof["create_count"] = 0
    return prof.get("create_count", 0)


# ------------------------------------------------------------------
# AI Settings Dialog
# ------------------------------------------------------------------


# ── PUBLIC ALIASES (FIX wildcard import untuk fungsi prefix _) ──────────
run_async = _run_async
minimize_chrome_windows = _minimize_chrome_windows
prompt_to_folder_name = _prompt_to_folder_name
parse_deepseek_response = _parse_deepseek_response
call_openai_compat = _call_openai_compat
call_claude = _call_claude
clean_style_tags = _clean_style_tags
prepare_ai = _prepare_ai
fallback_detect_genre = _fallback_detect_genre
prepare_fallback = _prepare_fallback
get_profile_abs = _get_profile_abs
save_profiles_raw    = _save_profiles_raw
load_prompt_config   = load_prompt_config
save_prompt_config   = save_prompt_config
get_active_prompt    = get_active_prompt
