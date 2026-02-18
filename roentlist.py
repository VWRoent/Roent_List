# -*- coding: utf-8 -*-
############################################################
# プログラム名: Roent.List
# バージョン: 1.0.0
# 制作日: 2026年2月18日
# 制作者: VWRoent（紫波レント）
# 使用技術: ChatGPT
# ライセンス: BSD 2-Clause License
# YouTube: https://www.youtube.com/@trans-cyp4365
# Twitter: https://x.com/VioWaveRoentgen
############################################################

"""
歌枠配信用 GUI（検索 / 詳細 / セットリスト / 登録 / タイムスタンプ / 設定）
+ OBS用 Viewer（HTML/CSS）を自動生成（obs_viewer/view.html, obs_viewer/style.css）
"""

import os
import sys
import json
import re
import sqlite3
import subprocess
import webbrowser
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

DB_FILE = "songs.db"
SETTINGS_FILE = "settings.json"

VIDEO_EXTS = "*.mp4 *.mkv *.webm"
AUDIO_EXTS = "*.mp3 *.wav"

# -------------------------
# DB
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn, table_name: str) -> set:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def _ensure_column(conn, table: str, col: str, coldef: str):
    if col not in _table_columns(conn, table):
        cur = conn.cursor()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        conn.commit()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            title_kana TEXT DEFAULT '',
            artist TEXT NOT NULL,
            artist_kana TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            provider_kana TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            lyrics TEXT DEFAULT '',
            credit_text TEXT DEFAULT '',
            video_path TEXT DEFAULT '',
            audio_path TEXT DEFAULT '',
            audio_url TEXT DEFAULT '',
            original_url TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    # 既存DB移行（念のため）
    _ensure_column(conn, "songs", "title_kana", "TEXT DEFAULT ''")
    _ensure_column(conn, "songs", "artist_kana", "TEXT DEFAULT ''")
    _ensure_column(conn, "songs", "provider_kana", "TEXT DEFAULT ''")

    conn.close()


def db_insert_song(data: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO songs (
            title, title_kana,
            artist, artist_kana,
            provider, provider_kana,
            keywords, lyrics, credit_text,
            video_path, audio_path,
            audio_url, original_url,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["title"], data.get("title_kana", ""),
            data["artist"], data.get("artist_kana", ""),
            data.get("provider", ""), data.get("provider_kana", ""),
            data.get("keywords", ""),
            data.get("lyrics", ""),
            data.get("credit_text", ""),
            data.get("video_path", ""),
            data.get("audio_path", ""),
            data.get("audio_url", ""),
            data.get("original_url", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def db_update_song(song_id: int, data: dict) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE songs SET
            title = ?,
            title_kana = ?,
            artist = ?,
            artist_kana = ?,
            provider = ?,
            provider_kana = ?,
            keywords = ?,
            lyrics = ?,
            credit_text = ?,
            video_path = ?,
            audio_path = ?,
            audio_url = ?,
            original_url = ?
        WHERE id = ?
        """,
        (
            data["title"], data.get("title_kana", ""),
            data["artist"], data.get("artist_kana", ""),
            data.get("provider", ""), data.get("provider_kana", ""),
            data.get("keywords", ""),
            data.get("lyrics", ""),
            data.get("credit_text", ""),
            data.get("video_path", ""),
            data.get("audio_path", ""),
            data.get("audio_url", ""),
            data.get("original_url", ""),
            song_id,
        ),
    )
    conn.commit()
    conn.close()


def db_get_song(song_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM songs WHERE id = ?", (song_id,))
    row = cur.fetchone()
    conn.close()
    return row


def db_search_songs(title="", artist="", provider="", keyword=""):
    title = (title or "").strip()
    artist = (artist or "").strip()
    provider = (provider or "").strip()
    keyword = (keyword or "").strip()

    where = []
    params = []

    if title:
        where.append("(title LIKE ? OR title_kana LIKE ?)")
        params.extend([f"%{title}%", f"%{title}%"])
    if artist:
        where.append("(artist LIKE ? OR artist_kana LIKE ?)")
        params.extend([f"%{artist}%", f"%{artist}%"])
    if provider:
        where.append("(provider LIKE ? OR provider_kana LIKE ?)")
        params.extend([f"%{provider}%", f"%{provider}%"])
    if keyword:
        where.append("keywords LIKE ?")
        params.append(f"%{keyword}%")

    sql = "SELECT * FROM songs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


# -------------------------
# Utility
# -------------------------
def exists_file(path: str) -> bool:
    path = (path or "").strip()
    return bool(path) and os.path.exists(path)


def open_path_with_default_app(path: str):
    path = (path or "").strip()
    if not path:
        raise FileNotFoundError("パスが空です。")
    if not os.path.exists(path):
        raise FileNotFoundError(f"見つかりません: {path}")

    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def safe_open_url(url: str):
    url = (url or "").strip()
    if url:
        webbrowser.open(url)


def song_line(row) -> str:
    t = (row["title"] or "").strip()
    a = (row["artist"] or "").strip()
    return f"{t} - {a}".strip(" -")


def format_hhmmss(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_youtube_ts(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h <= 0:
        return f"{m:02d}:{s:02d}"
    return f"{h:d}:{m:02d}:{s:02d}"


# -------------------------
# Theme
# -------------------------
THEMES = {
    "pastel_pink": {"name": "ピンク", "bg": "#fff7fb", "panel": "#ffe3f2", "panel2": "#fff0f8", "accent": "#ff7eb6", "text": "#222", "muted": "#555", "input_bg": "#fff", "input_fg": "#222"},
    "pastel_orange": {"name": "オレンジ", "bg": "#fff7ed", "panel": "#ffedd5", "panel2": "#fff3e6", "accent": "#fb923c", "text": "#1f2937", "muted": "#4b5563", "input_bg": "#fff", "input_fg": "#1f2937"},
    "pastel_blue": {"name": "ブルー", "bg": "#f3fbff", "panel": "#dff3ff", "panel2": "#eef9ff", "accent": "#60a5fa", "text": "#1f2937", "muted": "#4b5563", "input_bg": "#fff", "input_fg": "#1f2937"},
    "pastel_green": {"name": "グリーン", "bg": "#f6fff8", "panel": "#dcffe5", "panel2": "#eefef2", "accent": "#34d399", "text": "#1f2937", "muted": "#4b5563", "input_bg": "#fff", "input_fg": "#1f2937"},
    "pastel_lavender": {"name": "ラベンダー", "bg": "#faf5ff", "panel": "#eee1ff", "panel2": "#f7f0ff", "accent": "#a78bfa", "text": "#1f2937", "muted": "#4b5563", "input_bg": "#fff", "input_fg": "#1f2937"},
    "dark": {"name": "ダーク", "bg": "#1f232a", "panel": "#2b313a", "panel2": "#242a33", "accent": "#7dd3fc", "text": "#e5e7eb", "muted": "#9ca3af", "input_bg": "#111827", "input_fg": "#e5e7eb"},
}

# -------------------------
# OBS Viewer (HTML/CSS from scratch)
# -------------------------
VIEWER_STYLE_CSS = r"""@charset "UTF-8";
/* OBS向け: 透過背景 + 固定サイズレイアウト（サイズ/文字/配色は設定から） */
:root{
  --bg: rgba(0,0,0,0);
  --card: __CARD__;
  --card2: __CARD2__;
  --text: __TEXT__;
  --muted: __MUTED__;
  --accent: __ACCENT__;
  --border: __BORDER__;
  --shadow: __SHADOW__;
  --radius: 14px;

  /* fixed canvas size (px) */
  --w: __W__px;
  --h: __H__px;

  /* font sizes (px) */
  --title: __TITLE__px;
  --timer: __TIMER__px;
  --meta: __META__px;
  --section: __SECTION__px;
  --list: __LIST__px;
  --footer: __FOOTER__px;
}
html, body{
  margin:0; padding:0;
  width: var(--w);
  height: var(--h);
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: "Yu Gothic UI","Meiryo",system-ui,-apple-system,sans-serif;
}
.wrapper{
  width: var(--w);
  height: var(--h);
  padding: 18px;
  box-sizing: border-box;
}
.card{
  height: 100%;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 10px 30px var(--shadow);
  padding: 14px 16px;
  box-sizing: border-box;
  backdrop-filter: blur(6px);
  display: flex;
  flex-direction: column;
}
.h{
  display:flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}
.nowTitle{
  font-size: var(--title);
  font-weight: 800;
  line-height: 1.1;
  text-shadow: 0 2px 12px rgba(0,0,0,.25);
  flex: 1 1 auto;
  overflow:hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.timer{
  font-size: var(--timer);
  font-weight: 800;
  color: var(--accent);
  text-shadow: 0 2px 12px rgba(0,0,0,.25);
  flex: 0 0 auto;
}
.meta{
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 12px;
  background: var(--card2);
  border: 1px solid var(--border);
  font-size: var(--meta);
  color: var(--muted);
  min-height: calc(var(--meta) * 1.6);
}
.row{
  margin-top: 12px;
  flex: 1 1 auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  min-height: 0;
}
.col{
  background: var(--card2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  box-sizing: border-box;
  display:flex;
  flex-direction: column;
  min-height: 0;
}
.sectionTitle{
  font-size: var(--section);
  font-weight: 900;
  letter-spacing: .04em;
  margin-bottom: 8px;
  color: var(--text);
}
.list{
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  font-size: var(--list);
  line-height: 1.35;
  color: var(--text);
}
.list > div{
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 3px 0;
  border-bottom: 1px solid rgba(255,255,255,.10);
}
.list > div:last-child{ border-bottom: none; }
.footer{
  margin-top: 10px;
  display:flex;
  justify-content: space-between;
  align-items:center;
  font-size: var(--footer);
  color: var(--muted);
  opacity: .95;
}
.dt, .brand{
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.brand{
  font-weight: 800;
}
"""

def build_viewer_html(state: dict) -> str:
    """state を丸ごとHTMLに埋め込む（JS不要）"""
    now_title = state.get("now_title", "")
    timer = state.get("timer", "00:00:00")
    provider = state.get("now_provider", "")
    queue = state.get("queue", [])[:12]
    done = state.get("done", [])[:12]

    show_dt = bool(state.get("show_datetime", True))
    show_brand = bool(state.get("show_brand", True))
    dt_text = state.get("updated_at", "")
    brand_text = state.get("brand_text", "Roent.List")

    w = int(state.get("viewer_w", 800))
    h = int(state.get("viewer_h", 600))

    def esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    meta_html = f"音源: {esc(provider)} 様" if provider else "音源: &nbsp;"

    q_html = "\n".join([f"<div>{esc(x)}</div>" for x in queue]) if queue else "<div>—</div>"
    d_html = "\n".join([f"<div>{esc(x)}</div>" for x in done]) if done else "<div>—</div>"

    dt_html = esc(dt_text) if (show_dt and dt_text) else "&nbsp;"
    brand_html = esc(brand_text) if show_brand else "&nbsp;"

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={w}, height={h}, initial-scale=1" />
<meta http-equiv="refresh" content="1" />
<title>Roent.List Viewer</title>
<link rel="stylesheet" href="style.css" />
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="h">
        <div class="nowTitle">{esc(now_title)}</div>
        <div class="timer">{esc(timer)}</div>
      </div>

      <div class="meta">{meta_html}</div>

      <div class="row">
        <div class="col">
          <div class="sectionTitle">Queue</div>
          <div class="list">{q_html}</div>
        </div>
        <div class="col">
          <div class="sectionTitle">Done</div>
          <div class="list">{d_html}</div>
        </div>
      </div>

      <div class="footer">
        <div class="dt">{dt_html}</div>
        <div class="brand">{brand_html}</div>
      </div>
    </div>
  </div>
</body>
</html>
"""


# -------------------------
# GUI
# -------------------------
class KaraokeSetlistApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Roent.List 歌枠管理ソフト")
        self.geometry("900x900")
        self.minsize(650, 650)

        # 状態
        self.current_detail_id = None
        self.editing_song_id = None

        self.now_id = None
        self.now_start_sec = 0
        self.queue_ids = []
        self.finished_entries = []  # [{"song_id":int,"start_sec":int}]

        # タイマー
        self.timer_running = False
        self.timer_accum = 0.0
        self.timer_started_at = None
        self.timer_job = None
        self.elapsed_var = tk.StringVar(value="00:00:00")

        # スタンプ用
        self.session_events = []  # [{"song_id":int,"start_sec":int}]

        # テーマ
        self.settings = self._load_settings()

        # --- Settings migration / defaults ---
        # viewer_text_size (old) -> viewer_font_scale (new)
        if "viewer_font_scale" not in self.settings and "viewer_text_size" in self.settings:
            old = str(self.settings.get("viewer_text_size", "")).lower().strip()
            self.settings["viewer_font_scale"] = {"large": 2.0, "medium": 1.0, "small": 0.5}.get(old, 1.5)
        if "viewer_text_size" in self.settings:
            try:
                del self.settings["viewer_text_size"]
            except Exception:
                pass

        # Viewer defaults
        self.settings.setdefault("viewer_size", "800x600")           # 4:3
        self.settings.setdefault("viewer_font_scale", 1.5)           # 1.5x (default)
        self.settings.setdefault("viewer_theme", "same")             # same as window
        self.settings.setdefault("viewer_show_datetime", True)
        self.settings.setdefault("viewer_show_brand", True)
        self.settings.setdefault("viewer_brand_text", "Roent.List")

        # BGM (setlist tab)
        self.settings.setdefault("bgm_audio_path", "")
        self.settings.setdefault("bgm_video_path", "")
        # default: audio first, checkbox to prefer video
        self.settings.setdefault("bgm_prefer_video", False)

        # Setlist lyrics box (default small = mostly hidden)
        self.settings.setdefault("setlist_lyrics_box", "large")
        self.current_theme_key = self.settings.get("theme", "pastel_blue")


        # OBS Viewer 出力先（apply_theme より前に必ず用意する）
        self.viewer_dir = os.path.join(os.getcwd(), "obs_viewer")
        os.makedirs(self.viewer_dir, exist_ok=True)
        self._tk_text_widgets = []
        self._tk_list_widgets = []
        self._tk_canvas_widgets = []
        self._tk_label_widgets = []

        self._apply_fonts()
        self._build_setlist_fonts()
        self._build_styles_base()
        self._build_ui()
        self._apply_setlist_lyrics_box_size()
        self.apply_theme(self.current_theme_key, save=False)

        # OBS出力
        self.viewer_dir = os.path.join(os.getcwd(), "obs_viewer")
        os.makedirs(self.viewer_dir, exist_ok=True)
        self._ensure_viewer_files()
        self._viewer_prev = ""
        self._viewer_job = None
        self._viewer_tick()  # periodic

        self.run_search()

    # ---------- settings ----------
    def _load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- fonts/styles ----------
    def _apply_fonts(self):
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            text_font = tkfont.nametofont("TkTextFont")
            fixed_font = tkfont.nametofont("TkFixedFont")
            family = "Yu Gothic UI"
            default_font.configure(family=family, size=10)
            text_font.configure(family=family, size=10)
            fixed_font.configure(family=family, size=10)
        except Exception:
            pass

    def _build_setlist_fonts(self):
        try:
            base = tkfont.nametofont("TkTextFont")
            family = base.cget("family")
            base_size = int(base.cget("size"))
        except Exception:
            family = "Yu Gothic UI"
            base_size = 12

        lyrics_size = max(14, base_size * 2)
        list_size = max(10, int(lyrics_size * 2 / 3))

        self.setlist_lyrics_font = tkfont.Font(family=family, size=lyrics_size, weight="bold")
        self.setlist_list_font = tkfont.Font(family=family, size=list_size)

    def _build_styles_base(self):
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("TNotebook.Tab", padding=(14, 8))
        self.style.configure("TButton", padding=(10, 6))
        self.style.configure("TLabelframe", padding=(10, 8))
        self.style.configure("Treeview", rowheight=26)

    def apply_theme(self, theme_key: str, save: bool = True):
        if theme_key not in THEMES:
            theme_key = "pastel_blue"
        pal = THEMES[theme_key]
        self.current_theme_key = theme_key

        self.configure(bg=pal["bg"])
        self.style.configure(".", background=pal["bg"], foreground=pal["text"])
        self.style.configure("TFrame", background=pal["bg"])
        self.style.configure("TLabel", background=pal["bg"], foreground=pal["text"])
        self.style.configure("TNotebook", background=pal["bg"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=pal["panel"], foreground=pal["text"])
        self.style.map("TNotebook.Tab", background=[("selected", pal["panel2"])])

        self.style.configure("TLabelframe", background=pal["bg"], foreground=pal["text"])
        self.style.configure("TLabelframe.Label", background=pal["bg"], foreground=pal["text"])

        self.style.configure(
            "TEntry",
            fieldbackground=pal["input_bg"],
            foreground=pal["input_fg"],
            insertcolor=pal["input_fg"],
        )

        # Combobox: Windowsの既定配色だと（特にダーク時）白文字×薄いグレー背景で読みにくくなるため統一
        self.style.configure(
            "TCombobox",
            fieldbackground=pal["input_bg"],
            background=pal["panel"],
            foreground=pal["input_fg"],
            arrowcolor=pal["input_fg"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", pal["input_bg"]), ("disabled", pal["panel2"])],
            foreground=[("readonly", pal["input_fg"]), ("disabled", pal["muted"])],
            background=[("readonly", pal["panel"]), ("active", pal["panel2"]), ("disabled", pal["panel2"])],
        )
        self.style.configure("Muted.TLabel", background=pal["bg"], foreground=pal["muted"])

        self.style.configure("TButton", background=pal["panel"], foreground=pal["text"])
        self.style.map("TButton", background=[("active", pal["panel2"]), ("pressed", pal["panel2"])], foreground=[("disabled", pal["muted"])])

        self.style.configure("Treeview", background=pal["input_bg"], fieldbackground=pal["input_bg"], foreground=pal["text"])
        self.style.configure("Treeview.Heading", background=pal["panel"], foreground=pal["text"])

        for w in self._tk_text_widgets:
            try:
                w.configure(bg=pal["input_bg"], fg=pal["input_fg"], insertbackground=pal["input_fg"])
            except Exception:
                pass
        for w in self._tk_list_widgets:
            try:
                w.configure(bg=pal["input_bg"], fg=pal["input_fg"])
            except Exception:
                pass
        for w in self._tk_canvas_widgets:
            try:
                w.configure(bg=pal["bg"])
            except Exception:
                pass
        for w in self._tk_label_widgets:
            try:
                w.configure(bg=pal["bg"], fg=pal["text"])
            except Exception:
                pass

        self._write_viewer_css()

        if save:
            self.settings["theme"] = theme_key
            self._save_settings()
            if hasattr(self, "status_var"):
                self.status_var.set(f"スタイルを変更しました: {pal['name']}")

    # ---------- OBS viewer ----------
    def _ensure_viewer_files(self):
        self._write_viewer_css()

    def _write_viewer_css(self):
        """obs_viewer/style.css を設定に合わせて再生成"""
        self.viewer_dir = getattr(self, "viewer_dir", os.path.join(os.getcwd(), "obs_viewer"))
        os.makedirs(self.viewer_dir, exist_ok=True)

        # size
        size_str = (self.settings.get("viewer_size") or "800x600").lower().strip()
        mm = re.match(r"^(\d+)\s*x\s*(\d+)$", size_str)
        if mm:
            w, h = int(mm.group(1)), int(mm.group(2))
        else:
            w, h = 800, 600

        # font scale (default 1.5)
        scale_raw = self.settings.get("viewer_font_scale", 1.5)
        try:
            scale = float(scale_raw)
        except Exception:
            scale = 1.5
        if scale <= 0:
            scale = 1.5

        # viewer theme
        v_theme = (self.settings.get("viewer_theme") or "same").strip()
        if v_theme == "same":
            v_key = getattr(self, "current_theme_key", "pastel_blue")
        else:
            v_key = v_theme
        pal = THEMES.get(v_key, THEMES["pastel_blue"])

        def hex_to_rgba(hexcol: str, a: float) -> str:
            s = (hexcol or "").lstrip("#")
            if len(s) != 6:
                return f"rgba(20,20,24,{a})"
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
            return f"rgba({r},{g},{b},{a})"

        # palette -> viewer colors
        if v_key == "dark":
            card = "rgba(20,20,24,.72)"
            card2 = "rgba(20,20,24,.52)"
            textc = "rgba(255,255,255,.95)"
            muted = "rgba(255,255,255,.75)"
            border = "rgba(255,255,255,.18)"
            shadow = "rgba(0,0,0,.55)"
        else:
            card = hex_to_rgba(pal.get("panel", "#dff3ff"), 0.82)
            card2 = hex_to_rgba(pal.get("panel2", "#eef9ff"), 0.62)
            textc = pal.get("text", "#1f2937")
            muted = pal.get("muted", "#4b5563")
            border = "rgba(31,41,55,.18)"
            shadow = "rgba(0,0,0,.20)"

        accent = pal.get("accent", "#60a5fa")

        base = {"title": 26, "timer": 18, "meta": 14, "section": 14, "list": 16, "footer": 12}
        def sc(x):
            return max(6, int(round(x * scale)))

        css = VIEWER_STYLE_CSS
        css = css.replace("__CARD__", card)
        css = css.replace("__CARD2__", card2)
        css = css.replace("__TEXT__", str(textc))
        css = css.replace("__MUTED__", str(muted))
        css = css.replace("__ACCENT__", str(accent))
        css = css.replace("__BORDER__", border)
        css = css.replace("__SHADOW__", shadow)
        css = css.replace("__W__", str(w)).replace("__H__", str(h))
        css = css.replace("__TITLE__", str(sc(base["title"])))
        css = css.replace("__TIMER__", str(sc(base["timer"])))
        css = css.replace("__META__", str(sc(base["meta"])))
        css = css.replace("__SECTION__", str(sc(base["section"])))
        css = css.replace("__LIST__", str(sc(base["list"])))
        css = css.replace("__FOOTER__", str(sc(base["footer"])))

        css_path = os.path.join(self.viewer_dir, "style.css")
        try:
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(css)
        except Exception:
            pass


    def _build_viewer_state(self) -> dict:
        size_str = (self.settings.get("viewer_size") or "800x600").lower().strip()
        m = re.match(r"^(\d+)\s*x\s*(\d+)$", size_str)
        if m:
            vw, vh = int(m.group(1)), int(m.group(2))
        else:
            vw, vh = 800, 600

        show_dt = bool(self.settings.get("viewer_show_datetime", True))
        show_brand = bool(self.settings.get("viewer_show_brand", True))
        brand_text = self.settings.get("viewer_brand_text", "Roent.List")

        now_title = ""
        now_provider = ""
        if self.now_id is not None:
            row = db_get_song(self.now_id)
            if row:
                now_title = song_line(row)
                now_provider = (row["provider"] or "").strip()

        queue_lines = []
        for sid in self.queue_ids[:12]:
            r = db_get_song(sid)
            if r:
                queue_lines.append(song_line(r))

        done_lines = []
        for it in self.finished_entries[-12:][::-1]:
            sid = it["song_id"]
            sec = it["start_sec"]
            r = db_get_song(sid)
            if r:
                done_lines.append(f"{format_hhmmss(sec)}  {song_line(r)}")

        return {
            "viewer_w": vw,
            "viewer_h": vh,
            "now_title": now_title,
            "now_provider": now_provider,
            "timer": format_hhmmss(self.get_elapsed_seconds()),
            "queue": queue_lines,
            "done": done_lines,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "show_datetime": show_dt,
            "show_brand": show_brand,
            "brand_text": brand_text,
        }


    def _viewer_tick(self):
        state = self._build_viewer_state()
        html = build_viewer_html(state)
        if html != self._viewer_prev:
            self._viewer_prev = html
            try:
                with open(os.path.join(self.viewer_dir, "view.html"), "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass
        self._viewer_job = self.after(1000, self._viewer_tick)


    # ---------- setlist layout ----------
    def _get_setlist_lyrics_height(self) -> int:
        key = (self.settings.get("setlist_lyrics_box") or "small").strip().lower()
        return {"small": 2, "medium": 6, "large": 10}.get(key, 2)

    def _apply_setlist_lyrics_box_size(self):
        if hasattr(self, "now_lyrics_text"):
            try:
                self.now_lyrics_text.configure(height=self._get_setlist_lyrics_height())
            except Exception:
                pass

    # ---------- UI ----------
    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.tab_search = ttk.Frame(self.notebook)
        self.tab_detail = ttk.Frame(self.notebook)
        self.tab_setlist = ttk.Frame(self.notebook)
        self.tab_register = ttk.Frame(self.notebook)
        self.tab_stamp = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_search, text="検索")
        self.notebook.add(self.tab_detail, text="詳細")
        self.notebook.add(self.tab_setlist, text="セットリスト")
        self.notebook.add(self.tab_register, text="登録")
        self.notebook.add(self.tab_stamp, text="スタンプ")
        self.notebook.add(self.tab_settings, text="設定")

        self._build_search_tab()
        self._build_detail_tab()
        self._build_setlist_tab()
        self._build_register_tab()
        self._build_stamp_tab()
        self._build_settings_tab()

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", side="bottom")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _event):
        if self.notebook.select() == str(self.tab_stamp):
            self.refresh_stamp_view()

    # -------------------------
    # タイマー
    # -------------------------
    def get_elapsed_seconds(self) -> int:
        elapsed = self.timer_accum
        if self.timer_running and self.timer_started_at is not None:
            elapsed += (time.time() - self.timer_started_at)
        return int(elapsed)

    def toggle_timer(self):
        if not self.timer_running:
            self.timer_running = True
            self.timer_started_at = time.time()
            self.btn_timer.config(text="タイマー停止")
            self._timer_tick()
            self.status_var.set("タイマー開始")
        else:
            if self.timer_started_at is not None:
                self.timer_accum += (time.time() - self.timer_started_at)
            self.timer_running = False
            self.timer_started_at = None
            self.btn_timer.config(text="タイマー開始")
            if self.timer_job is not None:
                try:
                    self.after_cancel(self.timer_job)
                except Exception:
                    pass
                self.timer_job = None
            self.elapsed_var.set(format_hhmmss(self.get_elapsed_seconds()))
            self.status_var.set("タイマー停止")

    def _timer_tick(self):
        self.elapsed_var.set(format_hhmmss(self.get_elapsed_seconds()))
        self.timer_job = self.after(200, self._timer_tick)

    # -------------------------
    # 検索タブ
    # -------------------------
    def _build_search_tab(self):
        frm = ttk.Frame(self.tab_search, padding=10)
        frm.pack(fill="both", expand=True)

        filters = ttk.LabelFrame(frm, text="部分検索（ひらがなOK：ふりがな欄も検索します）")
        filters.pack(fill="x")

        self.q_title = tk.StringVar()
        self.q_artist = tk.StringVar()
        self.q_provider = tk.StringVar()
        self.q_keyword = tk.StringVar()

        ttk.Label(filters, text="曲名").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.q_title, width=26).grid(row=0, column=1, sticky="w", padx=8)
        ttk.Label(filters, text="アーティスト").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters, textvariable=self.q_artist, width=26).grid(row=0, column=3, sticky="w", padx=8)

        ttk.Label(filters, text="音源提供元").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(filters, textvariable=self.q_provider, width=26).grid(row=1, column=1, sticky="w", padx=8, pady=(6, 0))
        ttk.Label(filters, text="キーワード").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(filters, textvariable=self.q_keyword, width=26).grid(row=1, column=3, sticky="w", padx=8, pady=(6, 0))

        btns = ttk.Frame(filters)
        btns.grid(row=0, column=4, rowspan=2, sticky="ns", padx=(12, 0))
        ttk.Button(btns, text="検索", command=self.run_search, width=10).pack(pady=(0, 6))
        ttk.Button(btns, text="クリア", command=self.clear_search, width=10).pack()

        results = ttk.LabelFrame(frm, text="検索結果（ダブルクリックで詳細）")
        results.pack(fill="both", expand=True, pady=(10, 0))

        cols = ("id", "title", "artist", "provider", "keywords")
        self.tree = ttk.Treeview(results, columns=cols, show="headings", height=16)
        for c, t, w in [
            ("id", "ID", 60),
            ("title", "曲名", 260),
            ("artist", "アーティスト", 210),
            ("provider", "提供元", 160),
            ("keywords", "キーワード", 280),
        ]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=("e" if c == "id" else "w"))

        yscroll = ttk.Scrollbar(results, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        results.rowconfigure(0, weight=1)
        results.columnconfigure(0, weight=1)

        actions = ttk.Frame(results)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="詳細", command=self.open_selected_detail).pack(side="left")
        ttk.Button(actions, text="キューに追加", command=self.add_selected_to_queue).pack(side="left", padx=(10, 0))

        self.tree.bind("<Double-1>", lambda e: self.open_selected_detail())

    def clear_search(self):
        self.q_title.set("")
        self.q_artist.set("")
        self.q_provider.set("")
        self.q_keyword.set("")
        self.run_search()

    def run_search(self):
        rows = db_search_songs(self.q_title.get(), self.q_artist.get(), self.q_provider.get(), self.q_keyword.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in rows:
            self.tree.insert("", "end", values=(r["id"], r["title"], r["artist"], r["provider"], r["keywords"]))
        self.status_var.set(f"検索結果: {len(rows)} 件")

    def _selected_song_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel[0], "values")
        return int(vals[0]) if vals else None

    def open_selected_detail(self):
        sid = self._selected_song_id()
        if not sid:
            messagebox.showinfo("選択なし", "検索結果から曲を選択してください。")
            return
        self.show_detail(sid)

    def add_selected_to_queue(self):
        sid = self._selected_song_id()
        if not sid:
            messagebox.showinfo("選択なし", "検索結果から曲を選択してください。")
            return
        self.add_to_queue(sid)

    # -------------------------
    # 詳細タブ
    # -------------------------
    def _build_detail_tab(self):
        frm = ttk.Frame(self.tab_detail, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.LabelFrame(frm, text="基本情報（クリックで検索）")
        top.pack(fill="x")

        def make_link(parent, label_text):
            container = ttk.Frame(parent)
            ttk.Label(container, text=label_text).pack(side="left")
            link = tk.Label(container, text="-", cursor="hand2", font=("", 10, "underline"))
            link.pack(side="left", padx=(6, 0))
            self._tk_label_widgets.append(link)
            return container, link

        c1, self.link_title = make_link(top, "曲名")
        c2, self.link_artist = make_link(top, "アーティスト")
        c3, self.link_provider = make_link(top, "音源提供元")
        c4, self.link_keywords = make_link(top, "キーワード")

        c1.grid(row=0, column=0, sticky="w", padx=(0, 24), pady=(0, 6))
        c2.grid(row=0, column=1, sticky="w", padx=(0, 24), pady=(0, 6))
        c3.grid(row=1, column=0, sticky="w", padx=(0, 24), pady=(0, 6))
        c4.grid(row=1, column=1, sticky="w", padx=(0, 24), pady=(0, 6))

        urlfrm = ttk.LabelFrame(frm, text="URL")
        urlfrm.pack(fill="x", pady=(10, 0))

        ttk.Label(urlfrm, text="音源URL").grid(row=0, column=0, sticky="w")
        self.audio_url_var = tk.StringVar()
        self.audio_url_label = tk.Label(urlfrm, textvariable=self.audio_url_var, cursor="hand2")
        self.audio_url_label.grid(row=0, column=1, sticky="w", padx=8)
        self._tk_label_widgets.append(self.audio_url_label)

        ttk.Label(urlfrm, text="原曲URL").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.original_url_var = tk.StringVar()
        self.original_url_label = tk.Label(urlfrm, textvariable=self.original_url_var, cursor="hand2")
        self.original_url_label.grid(row=1, column=1, sticky="w", padx=8, pady=(4, 0))
        self._tk_label_widgets.append(self.original_url_label)

        self.audio_url_label.bind("<Button-1>", lambda e: safe_open_url(self.audio_url_var.get()))
        self.original_url_label.bind("<Button-1>", lambda e: safe_open_url(self.original_url_var.get()))

        mid = ttk.Frame(frm)
        mid.pack(fill="both", expand=True, pady=(10, 0))
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)
        mid.rowconfigure(1, weight=1)

        lyrics_box = ttk.LabelFrame(mid, text="歌詞（クリックで全文コピー）")
        credit_box = ttk.LabelFrame(mid, text="概要欄記載事項（クリックで全文コピー）")
        lyrics_box.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        credit_box.grid(row=1, column=0, sticky="nsew")

        self.lyrics_text = tk.Text(lyrics_box, wrap="word", height=8)
        self.credit_text = tk.Text(credit_box, wrap="word", height=6)
        self._tk_text_widgets.extend([self.lyrics_text, self.credit_text])

        ly_sb = ttk.Scrollbar(lyrics_box, orient="vertical", command=self.lyrics_text.yview)
        cr_sb = ttk.Scrollbar(credit_box, orient="vertical", command=self.credit_text.yview)
        self.lyrics_text.configure(yscrollcommand=ly_sb.set)
        self.credit_text.configure(yscrollcommand=cr_sb.set)

        self.lyrics_text.grid(row=0, column=0, sticky="nsew")
        ly_sb.grid(row=0, column=1, sticky="ns")
        lyrics_box.columnconfigure(0, weight=1)
        lyrics_box.rowconfigure(0, weight=1)

        self.credit_text.grid(row=0, column=0, sticky="nsew")
        cr_sb.grid(row=0, column=1, sticky="ns")
        credit_box.columnconfigure(0, weight=1)
        credit_box.rowconfigure(0, weight=1)

        self.lyrics_text.bind("<Button-1>", lambda e: self._copy_text(self.lyrics_text, "歌詞をコピーしました"))
        self.credit_text.bind("<Button-1>", lambda e: self._copy_text(self.credit_text, "概要欄記載事項をコピーしました"))

        paths = ttk.LabelFrame(frm, text="ローカルパス")
        paths.pack(fill="x", pady=(10, 0))
        ttk.Label(paths, text="動画パス").grid(row=0, column=0, sticky="w")
        self.video_path_var = tk.StringVar()
        ttk.Label(paths, textvariable=self.video_path_var).grid(row=0, column=1, sticky="w", padx=8)

        ttk.Label(paths, text="音源パス").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.audio_path_var2 = tk.StringVar()
        ttk.Label(paths, textvariable=self.audio_path_var2).grid(row=1, column=1, sticky="w", padx=8, pady=(4, 0))

        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="キューに追加", command=self.add_current_detail_to_queue).pack(side="left")
        ttk.Button(bottom, text="編集", command=self.edit_current_detail).pack(side="left", padx=(10, 0))
        ttk.Button(bottom, text="検索へ", command=lambda: self.notebook.select(self.tab_search)).pack(side="left", padx=(10, 0))

        self.link_title.bind("<Button-1>", lambda e: self._search_by("title"))
        self.link_artist.bind("<Button-1>", lambda e: self._search_by("artist"))
        self.link_provider.bind("<Button-1>", lambda e: self._search_by("provider"))
        self.link_keywords.bind("<Button-1>", lambda e: self._search_by("keywords"))

    def _copy_text(self, widget: tk.Text, msg: str):
        text = widget.get("1.0", "end").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(msg)

    def _search_by(self, field: str):
        if not self.current_detail_id:
            return
        row = db_get_song(self.current_detail_id)
        if not row:
            return
        self.q_title.set(row["title"] if field == "title" else "")
        self.q_artist.set(row["artist"] if field == "artist" else "")
        self.q_provider.set(row["provider"] if field == "provider" else "")
        self.q_keyword.set(row["keywords"] if field == "keywords" else "")
        self.notebook.select(self.tab_search)
        self.run_search()

    def show_detail(self, song_id: int):
        row = db_get_song(song_id)
        if not row:
            messagebox.showerror("エラー", "曲データが見つかりません。")
            return

        self.current_detail_id = song_id
        self.link_title.config(text=row["title"] or "-")
        self.link_artist.config(text=row["artist"] or "-")
        self.link_provider.config(text=row["provider"] or "-")
        self.link_keywords.config(text=row["keywords"] or "-")

        self.audio_url_var.set(row["audio_url"] or "")
        self.original_url_var.set(row["original_url"] or "")
        self.video_path_var.set(row["video_path"] or "")
        self.audio_path_var2.set(row["audio_path"] or "")

        self._set_text_readonly(self.lyrics_text, row["lyrics"] or "")
        self._set_text_readonly(self.credit_text, row["credit_text"] or "")

        self.notebook.select(self.tab_detail)
        self.status_var.set(f"詳細表示: ID={song_id}")

    def _set_text_readonly(self, widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def add_current_detail_to_queue(self):
        if not self.current_detail_id:
            messagebox.showinfo("未選択", "詳細表示中の曲がありません。")
            return
        self.add_to_queue(self.current_detail_id)

    def edit_current_detail(self):
        if not self.current_detail_id:
            return
        row = db_get_song(self.current_detail_id)
        if not row:
            return
        self.load_song_into_register(row)
        self.set_register_mode(edit_song_id=row["id"])
        self.notebook.select(self.tab_register)

    # -------------------------
    # セットリストタブ
    # -------------------------
    def _build_setlist_tab(self):
        frm = ttk.Frame(self.tab_setlist, padding=10)
        frm.pack(fill="both", expand=True)

        root_grid = ttk.Frame(frm)
        root_grid.pack(fill="both", expand=True)
        root_grid.columnconfigure(0, weight=1)
        root_grid.rowconfigure(0, weight=2)
        root_grid.rowconfigure(1, weight=3)

        # ---- Now box ----
        now_box = ttk.LabelFrame(root_grid, text="現在歌っている曲")
        now_box.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        now_box.columnconfigure(0, weight=1)
        now_box.rowconfigure(0, weight=0)  # header
        now_box.rowconfigure(1, weight=0)  # provider
        now_box.rowconfigure(2, weight=1)  # lyrics
        now_box.rowconfigure(3, weight=0, minsize=56)  # buttons

        header = ttk.Frame(now_box)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        header.columnconfigure(0, weight=1)

        self.now_title_var = tk.StringVar(value="（未設定）")
        ttk.Label(header, textvariable=self.now_title_var, font=("", 14, "bold")).grid(row=0, column=0, sticky="w")

        timer_box = ttk.Frame(header)
        timer_box.grid(row=0, column=1, sticky="e")
        ttk.Label(timer_box, text="経過", style="Muted.TLabel").pack(anchor="e")
        ttk.Label(timer_box, textvariable=self.elapsed_var, font=("", 12, "bold")).pack(anchor="e")

        self.now_provider_var = tk.StringVar(value="")
        ttk.Label(now_box, textvariable=self.now_provider_var, style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        lyrics_frame = ttk.Frame(now_box)
        lyrics_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        lyrics_frame.columnconfigure(0, weight=1)
        lyrics_frame.rowconfigure(0, weight=1)

        self.now_lyrics_text = tk.Text(lyrics_frame, wrap="word", font=self.setlist_lyrics_font, height=self._get_setlist_lyrics_height())
        self._tk_text_widgets.append(self.now_lyrics_text)
        ly_sb = ttk.Scrollbar(lyrics_frame, orient="vertical", command=self.now_lyrics_text.yview)
        self.now_lyrics_text.configure(yscrollcommand=ly_sb.set)
        self.now_lyrics_text.grid(row=0, column=0, sticky="nsew")
        ly_sb.grid(row=0, column=1, sticky="ns")

        btn_row = ttk.Frame(now_box)
        btn_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.btn_music = ttk.Button(btn_row, text="音楽", command=self.play_audio)
        self.btn_music.pack(side="left")
        self.btn_video = ttk.Button(btn_row, text="動画", command=self.play_video)
        self.btn_video.pack(side="left", padx=(8, 0))
        self.btn_detail = ttk.Button(btn_row, text="詳細", command=self.show_now_detail)
        self.btn_detail.pack(side="left", padx=(8, 0))

        self.btn_bgm = ttk.Button(btn_row, text="BGM", command=self.play_bgm)
        self.btn_bgm.pack(side="left", padx=(8, 0))
        ttk.Separator(btn_row, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(btn_row, text="歌詞送り▼", command=lambda: self.scroll_now_lyrics_half(1)).pack(side="left")
        ttk.Button(btn_row, text="歌詞戻し▲", command=lambda: self.scroll_now_lyrics_half(-1)).pack(side="left", padx=(8, 0))

        # ---- Bottom: queue & finished ----
        bottom = ttk.Frame(root_grid)
        bottom.grid(row=1, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        queue_box = ttk.LabelFrame(bottom, text="キュー（セットリスト）")
        fin_box = ttk.LabelFrame(bottom, text="歌い終わった曲")
        queue_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        fin_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        queue_box.columnconfigure(0, weight=1)
        queue_box.rowconfigure(0, weight=1)
        fin_box.columnconfigure(0, weight=1)
        fin_box.rowconfigure(0, weight=1)

        # Queue list + scrollbar
        q_list_frame = ttk.Frame(queue_box)
        q_list_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
        q_list_frame.columnconfigure(0, weight=1)
        q_list_frame.rowconfigure(0, weight=1)

        self.queue_list = tk.Listbox(q_list_frame, font=self.setlist_list_font)
        self._tk_list_widgets.append(self.queue_list)
        qsb = ttk.Scrollbar(q_list_frame, orient="vertical", command=self.queue_list.yview)
        self.queue_list.configure(yscrollcommand=qsb.set)
        self.queue_list.grid(row=0, column=0, sticky="nsew")
        qsb.grid(row=0, column=1, sticky="ns")

        self.queue_list.bind("<Return>", lambda e: self.select_song_from_queue())
        self.queue_list.bind("<Double-1>", lambda e: self.select_song_from_queue())

        qbtns = ttk.Frame(queue_box)
        qbtns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(qbtns, text="曲選択", command=self.select_song_from_queue).pack(side="left")
        ttk.Button(qbtns, text="削除", command=self.remove_queue_selected).pack(side="left", padx=(8, 0))
        ttk.Button(qbtns, text="上へ", command=lambda: self.move_queue(-1)).pack(side="left", padx=(8, 0))
        ttk.Button(qbtns, text="下へ", command=lambda: self.move_queue(1)).pack(side="left", padx=(8, 0))

        # Finished list + scrollbar
        f_list_frame = ttk.Frame(fin_box)
        f_list_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
        f_list_frame.columnconfigure(0, weight=1)
        f_list_frame.rowconfigure(0, weight=1)

        self.fin_list = tk.Listbox(f_list_frame, font=self.setlist_list_font)
        self._tk_list_widgets.append(self.fin_list)
        fsb = ttk.Scrollbar(f_list_frame, orient="vertical", command=self.fin_list.yview)
        self.fin_list.configure(yscrollcommand=fsb.set)
        self.fin_list.grid(row=0, column=0, sticky="nsew")
        fsb.grid(row=0, column=1, sticky="ns")

        fbtns = ttk.Frame(fin_box)
        fbtns.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.btn_timer = ttk.Button(fbtns, text="タイマー開始", command=self.toggle_timer)
        self.btn_timer.pack(side="left")
        ttk.Button(fbtns, text="履歴クリア", command=self.clear_finished).pack(side="left", padx=(10, 0))

        self._set_text_readonly(self.now_lyrics_text, "")
        self.refresh_now_view()

    def _visible_lines_in_text(self, widget: tk.Text) -> int:
        try:
            widget.update_idletasks()
            height_px = widget.winfo_height()
            f = tkfont.Font(font=widget["font"])
            line_px = max(1, int(f.metrics("linespace")))
            return max(1, height_px // line_px)
        except Exception:
            return 10

    def scroll_now_lyrics_half(self, direction: int):
        if direction not in (-1, 1):
            return
        lines = self._visible_lines_in_text(self.now_lyrics_text)
        half = max(1, lines // 2)
        self.now_lyrics_text.yview_scroll(direction * half, "units")

    def add_to_queue(self, song_id: int):
        row = db_get_song(song_id)
        if not row:
            messagebox.showerror("エラー", "曲データが見つかりません。")
            return
        self.queue_ids.append(song_id)
        self.queue_list.insert("end", song_line(row))
        self.status_var.set("キューに追加しました")

    def _move_now_to_finished(self):
        if self.now_id is None:
            return
        row_now = db_get_song(self.now_id)
        if not row_now:
            return
        self.finished_entries.append({"song_id": int(self.now_id), "start_sec": int(self.now_start_sec)})
        self.fin_list.insert("end", f"{format_hhmmss(self.now_start_sec)}  {song_line(row_now)}")

    def select_song_from_queue(self):
        sel = self.queue_list.curselection()
        if not sel:
            self.status_var.set("キューから曲を選択してください（EnterでもOK）")
            return
        idx = sel[0]

        self._move_now_to_finished()

        self.now_id = self.queue_ids.pop(idx)
        self.queue_list.delete(idx)

        self.now_start_sec = self.get_elapsed_seconds()
        self.session_events.append({"song_id": int(self.now_id), "start_sec": int(self.now_start_sec)})

        self.refresh_now_view()
        self.refresh_stamp_view()

    def refresh_now_view(self):
        if self.now_id is None:
            self.now_title_var.set("（未設定）")
            self.now_provider_var.set("")
            self._set_text_readonly(self.now_lyrics_text, "")
        else:
            row = db_get_song(self.now_id)
            if row:
                self.now_title_var.set(song_line(row))
                prov = (row["provider"] or "").strip()
                self.now_provider_var.set(f"音源: {prov} 様" if prov else "")
                self._set_text_readonly(self.now_lyrics_text, row["lyrics"] or "")
            else:
                self.now_title_var.set("（不明）")
                self.now_provider_var.set("")
                self._set_text_readonly(self.now_lyrics_text, "")
        self._update_now_controls()

    def show_now_detail(self):
        if self.now_id is None:
            return
        self.show_detail(self.now_id)

    def _update_now_controls(self):
        if self.now_id is None:
            self.btn_music.config(state="disabled")
            self.btn_video.config(state="disabled")
            self.btn_detail.config(state="disabled")
            return
        row = db_get_song(self.now_id)
        if not row:
            self.btn_music.config(state="disabled")
            self.btn_video.config(state="disabled")
            self.btn_detail.config(state="disabled")
            return
        self.btn_music.config(state="normal" if exists_file(row["audio_path"]) else "disabled")
        self.btn_video.config(state="normal" if exists_file(row["video_path"]) else "disabled")
        self.btn_detail.config(state="normal")

    def play_audio(self):
        if self.now_id is None:
            return
        row = db_get_song(self.now_id)
        if not row:
            return
        try:
            open_path_with_default_app(row["audio_path"])
            self.status_var.set("音源を開きました（既定アプリ）")
        except Exception as e:
            messagebox.showerror("再生エラー", str(e))

    def play_video(self):
        if self.now_id is None:
            return
        row = db_get_song(self.now_id)
        if not row:
            return
        try:
            open_path_with_default_app(row["video_path"])
            self.status_var.set("動画を開きました（既定アプリ）")
        except Exception as e:
            messagebox.showerror("再生エラー", str(e))


    def play_bgm(self):
        """設定タブで指定したBGM（動画/音源）を開く。現在曲は変更しない。"""
        vpath = str(self.settings.get("bgm_video_path", "") or "").strip()
        apath = str(self.settings.get("bgm_audio_path", "") or "").strip()

        def _exists(p: str) -> bool:
            try:
                return bool(p) and os.path.exists(p)
            except Exception:
                return False

        prefer_video = bool(self.settings.get("bgm_prefer_video", False))

        v_ok = _exists(vpath)
        a_ok = _exists(apath)

        if v_ok and a_ok:
            if prefer_video:
                target = vpath
                kind = "BGM動画"
            else:
                target = apath
                kind = "BGM音源"
        elif a_ok:
            target = apath
            kind = "BGM音源"
        elif v_ok:
            target = vpath
            kind = "BGM動画"
        else:
            if not vpath and not apath:
                messagebox.showinfo("BGM未設定", "設定タブでBGM用の動画または音源を指定してください。")
            else:
                messagebox.showwarning("BGMが見つかりません", "設定したBGMファイルが見つかりませんでした。\n設定タブでパスを確認してください。")
            return

        try:
            open_path_with_default_app(target)
            self.status_var.set(f"{kind}を開きました（既定アプリ）")
        except Exception as e:
            messagebox.showerror("再生エラー", str(e))

    def remove_queue_selected(self):
        sel = self.queue_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.queue_list.delete(idx)
        self.queue_ids.pop(idx)
        self.status_var.set("キューから削除しました")

    def move_queue(self, delta: int):
        sel = self.queue_list.curselection()
        if not sel:
            return
        idx = sel[0]
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= self.queue_list.size():
            return
        text = self.queue_list.get(idx)
        self.queue_list.delete(idx)
        self.queue_list.insert(new_idx, text)
        self.queue_list.selection_set(new_idx)
        sid = self.queue_ids.pop(idx)
        self.queue_ids.insert(new_idx, sid)

    def clear_finished(self):
        self.finished_entries = []
        self.fin_list.delete(0, "end")
        self.status_var.set("歌い終わり履歴をクリアしました")
        self.refresh_stamp_view()

    # -------------------------
    # 登録タブ
    # -------------------------
    def _build_register_tab(self):
        outer = ttk.Frame(self.tab_register)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer)
        self._tk_canvas_widgets.append(canvas)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        form = ttk.Frame(canvas, padding=12)
        canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self.register_mode_var = tk.StringVar(value="新規登録モード")
        ttk.Label(form, textvariable=self.register_mode_var, font=("", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.r_title = tk.StringVar()
        self.r_title_kana = tk.StringVar()
        self.r_artist = tk.StringVar()
        self.r_artist_kana = tk.StringVar()
        self.r_provider = tk.StringVar()
        self.r_provider_kana = tk.StringVar()
        self.r_keywords = tk.StringVar()
        self.r_video_path = tk.StringVar()
        self.r_audio_path = tk.StringVar()
        self.r_audio_url = tk.StringVar()
        self.r_original_url = tk.StringVar()

        r = 1
        ttk.Label(form, text="曲名 *").grid(row=r, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.r_title, width=48).grid(row=r, column=1, sticky="w", padx=8)

        r += 1
        ttk.Label(form, text="曲名ふりがな（ひらがな）").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.r_title_kana, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))

        r += 1
        ttk.Label(form, text="アーティスト名 *").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.r_artist, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(8, 0))

        r += 1
        ttk.Label(form, text="アーティスト名ふりがな（ひらがな）").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.r_artist_kana, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))

        r += 1
        ttk.Label(form, text="音源提供元").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.r_provider, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(8, 0))

        r += 1
        ttk.Label(form, text="提供元ふりがな（ひらがな）").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.r_provider_kana, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))

        r += 1
        ttk.Label(form, text="キーワード").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.r_keywords, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(8, 0))

        r += 1
        ttk.Label(form, text="歌詞").grid(row=r, column=0, sticky="nw", pady=(10, 0))
        self.r_lyrics = tk.Text(form, width=58, height=9, wrap="word")
        self._tk_text_widgets.append(self.r_lyrics)
        self.r_lyrics.grid(row=r, column=1, sticky="w", padx=8, pady=(10, 0))

        r += 1
        ttk.Label(form, text="概要欄記載事項").grid(row=r, column=0, sticky="nw", pady=(10, 0))
        self.r_credit = tk.Text(form, width=58, height=6, wrap="word")
        self._tk_text_widgets.append(self.r_credit)
        self.r_credit.grid(row=r, column=1, sticky="w", padx=8, pady=(10, 0))

        r += 1
        ttk.Label(form, text="動画 (mp4/mkv/webm) のパス").grid(row=r, column=0, sticky="w", pady=(10, 0))
        p1 = ttk.Frame(form)
        p1.grid(row=r, column=1, sticky="w", padx=8, pady=(10, 0))
        ttk.Entry(p1, textvariable=self.r_video_path, width=42).pack(side="left")
        ttk.Button(p1, text="参照", command=lambda: self.browse_file(self.r_video_path, [("Video", VIDEO_EXTS), ("All", "*.*")])).pack(side="left", padx=(8, 0))

        r += 1
        ttk.Label(form, text="音源 (mp3/wav) のパス").grid(row=r, column=0, sticky="w", pady=(6, 0))
        p2 = ttk.Frame(form)
        p2.grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))
        ttk.Entry(p2, textvariable=self.r_audio_path, width=42).pack(side="left")
        ttk.Button(p2, text="参照", command=lambda: self.browse_file(self.r_audio_path, [("Audio", AUDIO_EXTS), ("All", "*.*")])).pack(side="left", padx=(8, 0))

        r += 1
        ttk.Label(form, text="音源のURL").grid(row=r, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.r_audio_url, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(8, 0))

        r += 1
        ttk.Label(form, text="原曲のURL").grid(row=r, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(form, textvariable=self.r_original_url, width=48).grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))

        r += 1
        btnfrm = ttk.Frame(form)
        btnfrm.grid(row=r, column=1, sticky="w", padx=8, pady=(14, 0))

        self.submit_btn_text = tk.StringVar(value="登録する")
        ttk.Button(btnfrm, textvariable=self.submit_btn_text, command=self.submit_register, width=14).pack(side="left")
        ttk.Button(btnfrm, text="入力をクリア", command=self.clear_register_form, width=14).pack(side="left", padx=(10, 0))

        note = ttk.Label(form, text="* は必須です。検索欄にひらがなで入力しても、ふりがな欄を部分検索してヒットします。", style="Muted.TLabel", wraplength=520)
        note.grid(row=r + 1, column=1, sticky="w", padx=8, pady=(8, 12))

        self.set_register_mode(None)

    def browse_file(self, var: tk.StringVar, filetypes):
        path = filedialog.askopenfilename(title="ファイルを選択", filetypes=filetypes)
        if path:
            var.set(path)

    def set_register_mode(self, edit_song_id=None):
        self.editing_song_id = edit_song_id
        if edit_song_id is None:
            self.register_mode_var.set("新規登録モード")
            self.submit_btn_text.set("登録する")
        else:
            self.register_mode_var.set(f"編集モード（ID={edit_song_id}）")
            self.submit_btn_text.set("更新する")

    def load_song_into_register(self, row):
        self.r_title.set(row["title"] or "")
        self.r_title_kana.set(row["title_kana"] or "")
        self.r_artist.set(row["artist"] or "")
        self.r_artist_kana.set(row["artist_kana"] or "")
        self.r_provider.set(row["provider"] or "")
        self.r_provider_kana.set(row["provider_kana"] or "")
        self.r_keywords.set(row["keywords"] or "")
        self.r_video_path.set(row["video_path"] or "")
        self.r_audio_path.set(row["audio_path"] or "")
        self.r_audio_url.set(row["audio_url"] or "")
        self.r_original_url.set(row["original_url"] or "")
        self.r_lyrics.delete("1.0", "end")
        self.r_lyrics.insert("1.0", row["lyrics"] or "")
        self.r_credit.delete("1.0", "end")
        self.r_credit.insert("1.0", row["credit_text"] or "")

    def clear_register_form(self):
        self.set_register_mode(None)
        for v in [self.r_title, self.r_title_kana, self.r_artist, self.r_artist_kana, self.r_provider, self.r_provider_kana,
                  self.r_keywords, self.r_video_path, self.r_audio_path, self.r_audio_url, self.r_original_url]:
            v.set("")
        self.r_lyrics.delete("1.0", "end")
        self.r_credit.delete("1.0", "end")
        self.status_var.set("入力をクリアしました（新規登録モード）")

    def submit_register(self):
        title = self.r_title.get().strip()
        artist = self.r_artist.get().strip()
        if not title or not artist:
            messagebox.showwarning("入力不足", "曲名とアーティスト名は必須です。")
            return

        data = {
            "title": title,
            "title_kana": self.r_title_kana.get().strip(),
            "artist": artist,
            "artist_kana": self.r_artist_kana.get().strip(),
            "provider": self.r_provider.get().strip(),
            "provider_kana": self.r_provider_kana.get().strip(),
            "keywords": self.r_keywords.get().strip(),
            "lyrics": self.r_lyrics.get("1.0", "end").strip(),
            "credit_text": self.r_credit.get("1.0", "end").strip(),
            "video_path": self.r_video_path.get().strip(),
            "audio_path": self.r_audio_path.get().strip(),
            "audio_url": self.r_audio_url.get().strip(),
            "original_url": self.r_original_url.get().strip(),
        }

        if self.editing_song_id is None:
            new_id = db_insert_song(data)
            self.status_var.set(f"登録しました: ID={new_id}")
            self.notebook.select(self.tab_search)
            self.run_search()
        else:
            sid = int(self.editing_song_id)
            db_update_song(sid, data)
            self.status_var.set(f"更新しました: ID={sid}")
            self.run_search()
            self.show_detail(sid)

    # -------------------------
    # スタンプタブ
    # -------------------------
    def _build_stamp_tab(self):
        frm = ttk.Frame(self.tab_stamp, padding=10)
        frm.pack(fill="both", expand=True)

        top = ttk.LabelFrame(frm, text="YouTube用タイムスタンプ（生成してコピー）")
        top.pack(fill="x")

        btns = ttk.Frame(top)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="生成/更新", command=self.refresh_stamp_view).pack(side="left")
        ttk.Button(btns, text="コピー", command=self.copy_stamp_to_clipboard).pack(side="left", padx=(10, 0))

        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.stamp_text = tk.Text(body, wrap="none")
        self._tk_text_widgets.append(self.stamp_text)

        ysb = ttk.Scrollbar(body, orient="vertical", command=self.stamp_text.yview)
        xsb = ttk.Scrollbar(body, orient="horizontal", command=self.stamp_text.xview)
        self.stamp_text.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        self.stamp_text.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        self.refresh_stamp_view()

    def build_stamp_lines(self) -> list[str]:
        lines = ["00:00 開始"]
        for ev in self.session_events:
            row = db_get_song(ev["song_id"])
            title = row["title"] if row else "(不明)"
            lines.append(f"{format_youtube_ts(ev['start_sec'])} {title}")
        return lines

    def refresh_stamp_view(self):
        text = "\n".join(self.build_stamp_lines()).strip() + "\n"
        self.stamp_text.config(state="normal")
        self.stamp_text.delete("1.0", "end")
        self.stamp_text.insert("1.0", text)
        self.stamp_text.config(state="disabled")

    def copy_stamp_to_clipboard(self):
        text = self.stamp_text.get("1.0", "end").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("タイムスタンプをコピーしました")

    # -------------------------
    # 設定タブ
    # -------------------------
    def _build_settings_tab(self):
        frm = ttk.Frame(self.tab_settings, padding=12)
        frm.pack(fill="both", expand=True)

        # ---- Theme (Combo) ----
        box = ttk.LabelFrame(frm, text="ウィンドウスタイル")
        box.pack(fill="x")

        theme_items = [
            ("ピンク", "pastel_pink"),
            ("オレンジ", "pastel_orange"),
            ("ブルー", "pastel_blue"),
            ("グリーン", "pastel_green"),
            ("ラベンダー", "pastel_lavender"),
            ("ダーク", "dark"),
        ]
        key_to_label = {k: n for (n, k) in theme_items}
        label_to_key = {n: k for (n, k) in theme_items}

        self.theme_var = tk.StringVar(value=self.current_theme_key)

        row = ttk.Frame(box)
        row.pack(fill="x", padx=10, pady=10)
        ttk.Label(row, text="配色").pack(side="left")

        self.theme_combo = ttk.Combobox(row, state="readonly", width=18, values=[n for (n, _) in theme_items])
        self.theme_combo.set(key_to_label.get(self.current_theme_key, "ブルー"))
        self.theme_combo.pack(side="left", padx=(10, 0))

        def _theme_selected(_evt=None):
            sel = self.theme_combo.get().strip()
            key = label_to_key.get(sel, "pastel_blue")
            self.theme_var.set(key)
            self._on_theme_change()

        self.theme_combo.bind("<<ComboboxSelected>>", _theme_selected)

        tip = ttk.Label(frm, text="※ 設定は settings.json に保存され、次回起動時にも反映されます。", style="Muted.TLabel")
        tip.pack(anchor="w", pady=(10, 0))

        # ---- OBS Viewer ----
        obs = ttk.LabelFrame(frm, text="OBS Viewer 設定（HTML/CSS）")
        obs.pack(fill="x", pady=(12, 0))

        ttk.Label(
            obs,
            text="OBS のブラウザソースで「ローカルファイル」をONにして obs_viewer/view.html を指定してください。",
            style="Muted.TLabel",
            wraplength=720,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        ttk.Label(obs, text="保存先: " + os.path.join(os.getcwd(), "obs_viewer"), style="Muted.TLabel").pack(anchor="w", padx=10, pady=(0, 10))

        grid = ttk.Frame(obs)
        grid.pack(fill="x", padx=10, pady=(0, 10))
        grid.columnconfigure(1, weight=0)
        grid.columnconfigure(2, weight=1)

        # size
        ttk.Label(grid, text="全体サイズ").grid(row=0, column=0, sticky="w")
        current_size = str(self.settings.get("viewer_size", "800x600")).strip()

        size_opts = [
            "800x600 (4:3)  [default]",
            "640x480 (4:3)",
            "800x1067 (3:4)",
            "800x1422 (9:16)",
            "640x853 (3:4)",
            "640x1138 (9:16)",
            "カスタム",
        ]
        def _to_save_size(label: str) -> str:
            if label.strip() == "カスタム":
                return "custom"
            return label.split(" ")[0].strip()

        self.viewer_size_combo = ttk.Combobox(grid, values=size_opts, state="readonly", width=18)
        preset = next((opt for opt in size_opts if opt.startswith(current_size)), None)
        if preset:
            self.viewer_size_combo.set(preset)
        else:
            self.viewer_size_combo.set("カスタム")
        self.viewer_size_combo.grid(row=0, column=1, sticky="w", padx=10)

        custom = ttk.Frame(grid)
        custom.grid(row=0, column=2, sticky="w")
        ttk.Label(custom, text="W").pack(side="left")
        self.viewer_custom_w = tk.StringVar(value=current_size.split("x")[0] if "x" in current_size else "800")
        self.viewer_custom_h = tk.StringVar(value=current_size.split("x")[1] if "x" in current_size else "600")
        self.viewer_custom_w_entry = ttk.Entry(custom, textvariable=self.viewer_custom_w, width=6)
        self.viewer_custom_w_entry.pack(side="left", padx=(4, 8))
        ttk.Label(custom, text="H").pack(side="left")
        self.viewer_custom_h_entry = ttk.Entry(custom, textvariable=self.viewer_custom_h, width=6)
        self.viewer_custom_h_entry.pack(side="left", padx=(4, 8))
        self.viewer_custom_apply = ttk.Button(custom, text="適用", command=lambda: on_size_change(force_custom=True))
        self.viewer_custom_apply.pack(side="left")

        ttk.Label(grid, text="※ OBS側のブラウザソースの幅/高さも同じ値にすると扱いやすいです。", style="Muted.TLabel").grid(row=1, column=1, columnspan=2, sticky="w", padx=10, pady=(4, 0))

        def on_size_change(_evt=None, force_custom=False):
            sel = self.viewer_size_combo.get()
            if force_custom or sel.strip() == "カスタム":
                try:
                    w = int(self.viewer_custom_w.get().strip())
                    h = int(self.viewer_custom_h.get().strip())
                    if w < 100 or h < 100:
                        raise ValueError
                    self.settings["viewer_size"] = f"{w}x{h}"
                except Exception:
                    messagebox.showwarning("入力エラー", "カスタムサイズは 例: 800 x 600 のように数値で入力してください。")
                    return
                self.viewer_size_combo.set("カスタム")
            else:
                self.settings["viewer_size"] = _to_save_size(sel)

            self._save_settings()
            self._write_viewer_css()
            self.status_var.set(f"Viewerサイズ: {self.settings['viewer_size']}")

        def _toggle_custom():
            enable = (self.viewer_size_combo.get().strip() == "カスタム")
            st = "normal" if enable else "disabled"
            for wdg in [self.viewer_custom_w_entry, self.viewer_custom_h_entry, self.viewer_custom_apply]:
                try:
                    wdg.configure(state=st)
                except Exception:
                    pass

        def _size_selected(_evt=None):
            _toggle_custom()
            on_size_change(_evt)

        self.viewer_size_combo.bind("<<ComboboxSelected>>", _size_selected)
        _toggle_custom()

        # viewer font scale
        ttk.Label(grid, text="文字サイズ").grid(row=2, column=0, sticky="w", pady=(10, 0))

        scale_opts = ["1.5x (default)", "1.0x", "0.8x"]
        self.viewer_scale_combo = ttk.Combobox(grid, values=scale_opts, state="readonly", width=18)
        sv = self.settings.get("viewer_font_scale", 1.5)
        try:
            sv = float(sv)
        except Exception:
            sv = 1.5
        if abs(sv-1.0) < 1e-6:
            self.viewer_scale_combo.set("1.0x")
        elif abs(sv-0.8) < 1e-6:
            self.viewer_scale_combo.set("0.8x")
        else:
            self.viewer_scale_combo.set("1.5x (default)")
        self.viewer_scale_combo.grid(row=2, column=1, sticky="w", padx=10, pady=(10, 0))

        def on_scale_change(_evt=None):
            sel = self.viewer_scale_combo.get().strip()
            val = 1.5
            if sel.startswith("1.0"):
                val = 1.0
            elif sel.startswith("0.8"):
                val = 0.8
            self.settings["viewer_font_scale"] = val
            self._save_settings()
            self._write_viewer_css()
            self.status_var.set(f"Viewer文字サイズ: {val}x")

        self.viewer_scale_combo.bind("<<ComboboxSelected>>", on_scale_change)

        # viewer colors
        ttk.Label(grid, text="Viewer配色").grid(row=3, column=0, sticky="w", pady=(10, 0))

        v_opts = ["ウィンドウと同じ", "ピンク", "オレンジ", "ブルー", "グリーン", "ラベンダー", "ダーク"]
        self.viewer_theme_combo = ttk.Combobox(grid, values=v_opts, state="readonly", width=18)
        v_theme = str(self.settings.get("viewer_theme", "same")).strip()
        if v_theme == "same":
            self.viewer_theme_combo.set("ウィンドウと同じ")
        else:
            self.viewer_theme_combo.set(key_to_label.get(v_theme, "ウィンドウと同じ"))
        self.viewer_theme_combo.grid(row=3, column=1, sticky="w", padx=10, pady=(10, 0))

        def on_viewer_theme_change(_evt=None):
            sel = self.viewer_theme_combo.get().strip()
            if sel == "ウィンドウと同じ":
                self.settings["viewer_theme"] = "same"
            else:
                self.settings["viewer_theme"] = label_to_key.get(sel, "same")
            self._save_settings()
            self._write_viewer_css()
            self.status_var.set("Viewer配色を更新しました")

        self.viewer_theme_combo.bind("<<ComboboxSelected>>", on_viewer_theme_change)

        # footer options
        self.viewer_show_datetime_var = tk.BooleanVar(value=bool(self.settings.get("viewer_show_datetime", True)))
        self.viewer_show_brand_var = tk.BooleanVar(value=bool(self.settings.get("viewer_show_brand", True)))

        opt_row = ttk.Frame(grid)
        opt_row.grid(row=4, column=1, columnspan=2, sticky="w", padx=10, pady=(10, 0))
        ttk.Checkbutton(opt_row, text="日時を表示", variable=self.viewer_show_datetime_var, command=self._on_viewer_show_datetime).pack(side="left")
        ttk.Checkbutton(opt_row, text="Roent.List を表示", variable=self.viewer_show_brand_var, command=self._on_viewer_show_brand).pack(side="left", padx=(16, 0))

        # ---- Setlist Tab ----

        # ---- BGM ----
        bgm = ttk.LabelFrame(frm, text="BGM（セットリストタブ）")
        bgm.pack(fill="x", pady=(12, 0))

        self.bgm_video_var = tk.StringVar(value=str(self.settings.get("bgm_video_path", "") or ""))
        self.bgm_audio_var = tk.StringVar(value=str(self.settings.get("bgm_audio_path", "") or ""))
        self.bgm_prefer_video_var = tk.BooleanVar(value=bool(self.settings.get("bgm_prefer_video", False)))

        def _pick_bgm_video():
            path = filedialog.askopenfilename(
                title="BGM用の動画を選択",
                filetypes=[
                    ("Video", "*.mp4 *.mkv *.webm"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return
            self.bgm_video_var.set(path)
            self.settings["bgm_video_path"] = path
            self._save_settings()
            self.status_var.set("BGM動画を設定しました")

        def _pick_bgm_audio():
            path = filedialog.askopenfilename(
                title="BGM用の音源を選択",
                filetypes=[
                    ("Audio", "*.mp3 *.wav"),
                    ("All files", "*.*"),
                ],
            )
            if not path:
                return
            self.bgm_audio_var.set(path)
            self.settings["bgm_audio_path"] = path
            self._save_settings()
            self.status_var.set("BGM音源を設定しました")

        def _on_bgm_priority_toggle():
            self.settings["bgm_prefer_video"] = bool(self.bgm_prefer_video_var.get())
            self._save_settings()
            self.status_var.set("BGMの優先設定を更新しました")

        def _clear_bgm():
            self.bgm_video_var.set("")
            self.bgm_audio_var.set("")
            self.settings["bgm_video_path"] = ""
            self.settings["bgm_audio_path"] = ""
            self._save_settings()
            self.status_var.set("BGM設定をクリアしました")

        r0 = ttk.Frame(bgm)
        r0.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(r0, text="動画").pack(side="left")
        ttk.Entry(r0, textvariable=self.bgm_video_var, width=60).pack(side="left", padx=(10, 8), fill="x", expand=True)
        ttk.Button(r0, text="参照", command=_pick_bgm_video).pack(side="left")

        r1 = ttk.Frame(bgm)
        r1.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(r1, text="音源").pack(side="left")
        ttk.Entry(r1, textvariable=self.bgm_audio_var, width=60).pack(side="left", padx=(10, 8), fill="x", expand=True)
        ttk.Button(r1, text="参照", command=_pick_bgm_audio).pack(side="left")

        r2 = ttk.Frame(bgm)
        r2.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(r2, text="クリア", command=_clear_bgm).pack(side="left")
        ttk.Checkbutton(r2, text="動画を優先（チェック時）", variable=self.bgm_prefer_video_var, command=_on_bgm_priority_toggle).pack(side="left", padx=(10, 0))
        ttk.Label(r2, text="※ デフォルトは音源優先です。", style="Muted.TLabel").pack(side="left", padx=(10, 0))

        sl = ttk.LabelFrame(frm, text="セットリスト表示")
        sl.pack(fill="x", pady=(12, 0))

        g2 = ttk.Frame(sl)
        g2.pack(fill="x", padx=10, pady=10)
        ttk.Label(g2, text="歌詞ボックスサイズ").pack(side="left")

        lb_opts = [("小（1/5）", "small"), ("中（標準）", "medium"), ("大（広め）", "large")]
        key2name = {k: n for (n, k) in lb_opts}
        name2key = {n: k for (n, k) in lb_opts}

        self.setlist_lyrics_combo = ttk.Combobox(g2, state="readonly", width=14, values=[n for (n, _) in lb_opts])
        self.setlist_lyrics_combo.set(key2name.get(str(self.settings.get("setlist_lyrics_box", "large")), "大（広め）"))
        self.setlist_lyrics_combo.pack(side="left", padx=(10, 0))

        def on_setlist_lyrics_change(_evt=None):
            sel = self.setlist_lyrics_combo.get().strip()
            self.settings["setlist_lyrics_box"] = name2key.get(sel, "small")
            self._save_settings()
            self._apply_setlist_lyrics_box_size()
            self.status_var.set("セットリスト歌詞ボックスサイズを更新しました")

        self.setlist_lyrics_combo.bind("<<ComboboxSelected>>", on_setlist_lyrics_change)

    def _on_theme_change(self):
        self.apply_theme(self.theme_var.get(), save=True)
    def _on_viewer_show_datetime(self):
        self.settings["viewer_show_datetime"] = bool(self.viewer_show_datetime_var.get())
        self._save_settings()
        self.status_var.set("Viewer日時表示を更新しました")

    def _on_viewer_show_brand(self):
        new_val = bool(self.viewer_show_brand_var.get())
        if not new_val:
            messagebox.showinfo("お願い", "htmlからRoent.Listの表示を消す際は概要欄にRoent.Listの表記をお願いします。")
        self.settings["viewer_show_brand"] = new_val
        self._save_settings()
        self.status_var.set("Viewer Roent.List 表示を更新しました")




if __name__ == "__main__":
    init_db()
    app = KaraokeSetlistApp()
    app.mainloop()
