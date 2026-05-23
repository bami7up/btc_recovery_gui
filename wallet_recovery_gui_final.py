#!/usr/bin/env python3
"""
Wallet Recovery GUI — инструмент восстановления пароля СВОЕГО Bitcoin wallet.dat.

Python: 3.12 (обязательно)
GUI: tkinter

Возможности:
  - ввод слов, фраз, цифр, спецсимволов;
  - шаблоны генерации через токены:
      {W} = слово
      {P} = фраза
      {N} = цифры
      {S} = спецсимволы
  - мутации регистра:
      word / Word / WORD
      swapcase
      PaRoL
      pArOl
  - конвертация русской раскладки в английскую;
  - запуск btcrecover через venv;
  - очередь запусков: plain / typos 1 / typos 2 / capslock;
  - мониторинг: время, сценарий, активность, попытка парсинга скорости;
  - извлечение hash через bitcoin2john.py;
  - запуск Hashcat mode 11300;
  - проверка баланса BTC-адресов через Esplora API.

Важно:
  - Работай только с копией wallet.dat.
  - Скрипт предназначен для восстановления собственного кошелька.
"""

import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
import venv as venv_mod
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk


# ── Цвета и стили ─────────────────────────────────────────────────────────────
BG = "#0d1117"
BG2 = "#161b22"
BG3 = "#21262d"
ACCENT = "#f7931a"
ACCENT2 = "#ff6b35"
TEXT = "#e6edf3"
TEXT_DIM = "#8b949e"
GREEN = "#3fb950"
RED = "#f85149"
BORDER = "#30363d"
BLUE = "#58a6ff"
PURPLE = "#d2a8ff"

FONT_TITLE = ("Consolas", 18, "bold")
FONT_HEAD = ("Consolas", 11, "bold")
FONT_BODY = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)
FONT_MONO = ("Courier New", 9)

APP_DIR = Path.home() / ".wallet_recovery_gui"
APP_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = APP_DIR / "recovery_data.json"

DEFAULT_WARNING_LIMIT = 10_000_000
PROGRESS_EVERY = 100_000

TOKENS = ("{W}", "{P}", "{N}", "{S}")

DEFAULT_TEMPLATES = [
    "{W}",
    "{W}{N}",
    "{W}{S}{N}",
    "{S}{W}{N}",
    "{N}{W}{S}",
    "{P}",
    "{P}{N}",
    "{P}{S}{N}",
    "{S}{P}{N}",
    "{N}{P}{S}",
]

RU_TO_EN = str.maketrans(
    "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХъФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ",
    "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~",
)


def ru_to_en(text: str) -> str:
    return text.translate(RU_TO_EN)


def unique_keep_order(items):
    seen = set()
    result = []
    for item in items:
        item = str(item).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def alt_case(text: str) -> str:
    out = []
    upper = True
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)


def alt_case_inverse(text: str) -> str:
    out = []
    upper = False
    for ch in text:
        if ch.isalpha():
            out.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            out.append(ch)
    return "".join(out)

def _get_python_version(py_path: Path):
    try:
        result = subprocess.run(
            [str(py_path), "-c", 'import sys; print("{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro))'],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def _is_python_312(py_path: Path) -> bool:
    version = _get_python_version(py_path)
    return bool(version and version.startswith("3.12."))



class TagList(tk.Frame):
    def __init__(self, master, color=ACCENT, height=180, **kwargs):
        super().__init__(master, bg=BG2, **kwargs)
        self.color = color
        self.items = []
        self._widgets = []

        row = tk.Frame(self, bg=BG2)
        row.pack(fill="x", padx=8, pady=(8, 4))

        self.entry = tk.Entry(
            row,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=color,
            highlightbackground=BORDER,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
        self.entry.bind("<Return>", lambda _event: self._add())

        tk.Button(
            row,
            text="+ Добавить",
            bg=color,
            fg=BG,
            font=FONT_HEAD,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT2,
            activeforeground=BG,
            command=self._add,
            padx=10,
        ).pack(side="right")

        self.canvas = tk.Canvas(self, bg=BG2, highlightthickness=0, height=height)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.inner = tk.Frame(self.canvas, bg=BG2)
        self.win_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw", width=1)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win_id, width=e.width))
        self.canvas.bind("<Enter>", self._bind_scroll)
        self.canvas.bind("<Leave>", self._unbind_scroll)

    def _bind_scroll(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(1, "units"))

    def _unbind_scroll(self, _event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _add(self):
        value = self.entry.get().strip()
        self.entry.delete(0, "end")
        self.add_item(value)

    def add_item(self, value):
        value = str(value).strip()
        if not value or value in self.items:
            return
        self.items.append(value)
        self._render(value)

    def _render(self, value):
        row = tk.Frame(self.inner, bg=BG3, pady=3)
        row.pack(fill="x", pady=2, padx=2)

        tk.Label(
            row,
            text=value,
            bg=BG3,
            fg=TEXT,
            font=FONT_BODY,
            anchor="w",
            padx=8,
        ).pack(side="left", fill="x", expand=True)

        def remove(v=value, r=row):
            if v in self.items:
                self.items.remove(v)
            if r in self._widgets:
                self._widgets.remove(r)
            r.destroy()

        tk.Button(
            row,
            text="✕",
            bg=BG3,
            fg=RED,
            font=FONT_SMALL,
            relief="flat",
            cursor="hand2",
            command=remove,
            activebackground=BG3,
            activeforeground=RED,
            padx=6,
        ).pack(side="right")
        self._widgets.append(row)

    def get(self):
        return list(self.items)

    def set(self, items):
        self.items.clear()
        for widget in list(self._widgets):
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self._widgets.clear()

        for item in unique_keep_order(items):
            self.items.append(item)
            self._render(item)


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Wallet Recovery Tool")
        self.geometry("1200x860")
        self.minsize(980, 720)
        self.configure(bg=BG)

        self.wallet_path = tk.StringVar(value="")
        self.dict_path = tk.StringVar(value="passwords.txt")
        self.btcrecover_path = tk.StringVar(value="")
        self.btr_dir = tk.StringVar(value=str(Path.cwd() / "btcrecover"))
        self.venv_dir = tk.StringVar(value=str(Path.cwd() / "btcrecover_venv"))
        self.work_dir = tk.StringVar(value=str(Path.cwd()))

        self.proc = None
        self.hashcat_proc = None
        self._running = False
        self._generating = False
        self._stop_requested = False

        self._run_started_at = None
        self._scenario_started_at = None
        self._last_output_at = None
        self._dict_line_count = 0
        self._current_scenario = "—"
        self._last_speed = "—"
        self._last_checked_password = "—"
        self._autosave_job = None

        self._build_ui()
        self._sync_btr_path()
        self._load_data()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_autosave()
        self.after(300, self._check_venv)

    # ── Общий UI ──────────────────────────────────────────────────────────────
    def _btn(self, parent, text, command, color, big=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=BG if color not in (BORDER, TEXT_DIM) else TEXT,
            font=FONT_HEAD if big else FONT_BODY,
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT2,
            activeforeground=BG,
            padx=14 if big else 8,
            pady=6 if big else 3,
        )

    def _section(self, parent, title, color):
        return tk.LabelFrame(
            parent,
            text=f"  {title}  ",
            bg=BG2,
            fg=color,
            font=FONT_HEAD,
            bd=1,
            relief="solid",
        )

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG3,
            foreground=TEXT_DIM,
            padding=[18, 8],
            font=FONT_HEAD,
            borderwidth=0,
        )
        style.map("TNotebook.Tab", background=[("selected", BG2)], foreground=[("selected", ACCENT)])
        style.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG2, borderwidth=0, arrowcolor=TEXT_DIM)

    def _build_ui(self):
        header = tk.Frame(self, bg=BG, pady=14)
        header.pack(fill="x", padx=20)

        tk.Label(header, text="₿", font=("Consolas", 28, "bold"), fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(header, text="  WALLET RECOVERY", font=FONT_TITLE, fg=TEXT, bg=BG).pack(side="left")
        tk.Label(header, text="  password tool", font=("Consolas", 11), fg=TEXT_DIM, bg=BG).pack(side="left", pady=(6, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)
        self._style()

        quick_guide = tk.Label(
            self,
            text="Быстрый порядок: 1) Данные → 2) Генерация → 3) btcrecover → 4) Hashcat (опционально) → 5) Баланс.",
            bg=BG2,
            fg=TEXT,
            font=FONT_SMALL,
            anchor="w",
            padx=10,
            pady=6,
        )
        quick_guide.pack(fill="x", padx=20, pady=(8, 4))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=20, pady=12)

        self.tab_data = tk.Frame(notebook, bg=BG)
        self.tab_gen = tk.Frame(notebook, bg=BG)
        self.tab_run = tk.Frame(notebook, bg=BG)
        self.tab_hash = tk.Frame(notebook, bg=BG)
        self.tab_balance = tk.Frame(notebook, bg=BG)
        self.tab_cfg = tk.Frame(notebook, bg=BG)
        self.tab_help = tk.Frame(notebook, bg=BG)

        notebook.add(self.tab_data, text="📝  Данные")
        notebook.add(self.tab_gen, text="⚙️  Генерация")
        notebook.add(self.tab_run, text="🔍  btcrecover")
        notebook.add(self.tab_hash, text="⚡  Hashcat")
        notebook.add(self.tab_balance, text="💰  Баланс")
        notebook.add(self.tab_cfg, text="🔧  Настройки")
        notebook.add(self.tab_help, text="❔  Где скачать")

        self._build_data_tab()
        self._build_gen_tab()
        self._build_run_tab()
        self._build_hashcat_tab()
        self._build_balance_tab()
        self._build_cfg_tab()
        self._build_help_tab()

    # ── Вкладка Данные ────────────────────────────────────────────────────────
    def _build_data_tab(self):
        parent = self.tab_data

        tk.Label(
            parent,
            text="Заполни то, что реально мог использовать. Фантазии сюда не надо: словарь потом мстит размером.",
            bg=BG,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=6, pady=(4, 8))

        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="both", expand=True)
        for col in (0, 1):
            grid.columnconfigure(col, weight=1)
        for row in (0, 1):
            grid.rowconfigure(row, weight=1)

        f_words = self._section(grid, "Слова {W}", ACCENT)
        f_phrases = self._section(grid, "Фразы {P}", BLUE)
        f_numbers = self._section(grid, "Цифры {N}", GREEN)
        f_specials = self._section(grid, "Спецсимволы {S}", PURPLE)

        f_words.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        f_phrases.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        f_numbers.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        f_specials.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)

        tk.Label(
            f_phrases,
            text="Пиши фразу через пробел. Генератор сделает варианты: слитно и через нижнее подчёркивание.",
            bg=BG2,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=8, pady=(4, 0))

        self.lst_words = TagList(f_words, color=ACCENT)
        self.lst_phrases = TagList(f_phrases, color=BLUE)
        self.lst_numbers = TagList(f_numbers, color=GREEN)
        self.lst_specials = TagList(f_specials, color=PURPLE)

        self.lst_words.pack(fill="both", expand=True)
        self.lst_phrases.pack(fill="both", expand=True)
        self.lst_numbers.pack(fill="both", expand=True)
        self.lst_specials.pack(fill="both", expand=True)

        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", padx=6, pady=(4, 2))
        self._btn(bar, "💾 Сохранить данные", self._save_data, ACCENT).pack(side="left")
        self._btn(bar, "🗑 Очистить всё", self._clear_all, RED).pack(side="left", padx=8)

    # ── Вкладка Генерация ─────────────────────────────────────────────────────
    def _build_gen_tab(self):
        parent = self.tab_gen

        opts = self._section(parent, "Опции генерации", ACCENT)
        opts.pack(fill="x", padx=8, pady=8)

        self.var_caps = tk.BooleanVar(value=True)
        self.var_ru2en = tk.BooleanVar(value=True)
        self.var_reverse = tk.BooleanVar(value=False)
        self.var_swapcase = tk.BooleanVar(value=True)
        self.var_altcase = tk.BooleanVar(value=True)
        self.var_altcase_inv = tk.BooleanVar(value=True)
        self.var_use_empty_num = tk.BooleanVar(value=True)
        self.var_use_empty_spec = tk.BooleanVar(value=True)

        def chk(text, var):
            tk.Checkbutton(
                opts,
                text=text,
                variable=var,
                bg=BG2,
                fg=TEXT,
                selectcolor=BG3,
                activebackground=BG2,
                activeforeground=ACCENT,
                font=FONT_BODY,
            ).pack(anchor="w", padx=16, pady=2)

        chk("Варианты регистра: word / Word / WORD", self.var_caps)
        chk("Инвертировать регистр: Password -> pASSWORD", self.var_swapcase)
        chk("Чередование регистра: PaRoL", self.var_altcase)
        chk("Обратное чередование: pArOl", self.var_altcase_inv)
        chk("Конвертировать русскую раскладку в английскую", self.var_ru2en)
        chk("Добавить реверс каждого слова/фразы", self.var_reverse)
        chk("Разрешить пустые цифры {N}", self.var_use_empty_num)
        chk("Разрешить пустые спецсимволы {S}", self.var_use_empty_spec)

        tpl_frame = self._section(parent, "Шаблоны порядка", BLUE)
        tpl_frame.pack(fill="both", expand=True, padx=8, pady=6)

        tk.Label(
            tpl_frame,
            text="Токены: {W}=слово, {P}=фраза, {N}=цифры, {S}=спецсимволы. Примеры: {W}_{N}, {S}{P}{N}, {W}-{N}.",
            bg=BG2,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=8, pady=(6, 0))

        self.lst_templates = TagList(tpl_frame, color=BLUE, height=150)
        self.lst_templates.pack(fill="both", expand=True)
        self.lst_templates.set(DEFAULT_TEMPLATES)

        tpl_btns = tk.Frame(tpl_frame, bg=BG2)
        tpl_btns.pack(fill="x", padx=8, pady=(0, 8))
        self._btn(tpl_btns, "↩ Вернуть шаблоны по умолчанию", self._reset_templates, BLUE).pack(side="left")
        self._btn(tpl_btns, "🧮 Оценить размер", self._estimate_dialog, GREEN).pack(side="left", padx=8)

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="Выходной файл:", bg=BG, fg=TEXT_DIM, font=FONT_BODY).pack(side="left")
        self.out_path = tk.Entry(
            row,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
            width=50,
        )
        self.out_path.insert(0, "passwords.txt")
        self.out_path.pack(side="left", ipady=4, padx=8)
        self._btn(row, "📂", self._pick_out, BORDER).pack(side="left")

        self.btn_generate = self._btn(parent, "⚡ СГЕНЕРИРОВАТЬ СЛОВАРЬ", self._generate, ACCENT, big=True)
        self.btn_generate.pack(pady=10)

        self.gen_log = scrolledtext.ScrolledText(
            parent,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            height=11,
            relief="flat",
            state="disabled",
            insertbackground=TEXT,
        )
        self.gen_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ── Вкладка btcrecover ────────────────────────────────────────────────────
    def _build_run_tab(self):
        parent = self.tab_run

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=8, pady=8)

        wallet_frame = self._section(top, "wallet.dat — только копия", ACCENT)
        wallet_frame.pack(fill="x", pady=(0, 6))
        wallet_row = tk.Frame(wallet_frame, bg=BG2)
        wallet_row.pack(fill="x", padx=8, pady=6)

        tk.Entry(
            wallet_row,
            textvariable=self.wallet_path,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(wallet_row, "📂 Выбрать", self._pick_wallet, ACCENT).pack(side="left", padx=(8, 0))

        dict_frame = self._section(top, "Словарь passwords.txt", GREEN)
        dict_frame.pack(fill="x", pady=(0, 6))
        dict_row = tk.Frame(dict_frame, bg=BG2)
        dict_row.pack(fill="x", padx=8, pady=6)

        tk.Entry(
            dict_row,
            textvariable=self.dict_path,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=GREEN,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(dict_row, "📂 Выбрать", self._pick_dict, GREEN).pack(side="left", padx=(8, 0))

        run_frame = self._section(top, "Сценарии запуска", BLUE)
        run_frame.pack(fill="x", pady=(0, 6))

        self.var_run_plain = tk.BooleanVar(value=True)
        self.var_run_typos1 = tk.BooleanVar(value=True)
        self.var_run_typos2 = tk.BooleanVar(value=True)
        self.var_run_capslock = tk.BooleanVar(value=True)

        run_row = tk.Frame(run_frame, bg=BG2)
        run_row.pack(fill="x", padx=12, pady=8)

        def run_chk(text, var):
            tk.Checkbutton(
                run_row,
                text=text,
                variable=var,
                bg=BG2,
                fg=TEXT,
                selectcolor=BG3,
                activebackground=BG2,
                activeforeground=ACCENT,
                font=FONT_BODY,
            ).pack(side="left", padx=(0, 18))

        run_chk("1. Просто словарь", self.var_run_plain)
        run_chk("2. Typos 1", self.var_run_typos1)
        run_chk("3. Typos 2", self.var_run_typos2)
        run_chk("4. CapsLock", self.var_run_capslock)

        button_row = tk.Frame(parent, bg=BG)
        button_row.pack(pady=6)
        self.btn_start = self._btn(button_row, "▶ ЗАПУСТИТЬ btcrecover", self._start_btcrecover, GREEN, big=True)
        self.btn_start.pack(side="left")
        self.btn_stop = self._btn(button_row, "⏹ СТОП", self._stop_btcrecover, RED, big=True)
        self.btn_stop.pack(side="left", padx=10)
        self.btn_stop.config(state="disabled")

        self.status_var = tk.StringVar(value="Готов к запуску")
        self.status_lbl = tk.Label(parent, textvariable=self.status_var, bg=BG, fg=TEXT_DIM, font=FONT_SMALL)
        self.status_lbl.pack()

        stats = self._section(parent, "Мониторинг", BLUE)
        stats.pack(fill="x", padx=8, pady=(6, 6))
        stats_grid = tk.Frame(stats, bg=BG2)
        stats_grid.pack(fill="x", padx=10, pady=8)
        for col in range(4):
            stats_grid.columnconfigure(col, weight=1)

        self.progress_scenario_var = tk.StringVar(value="Сценарий: —")
        self.progress_elapsed_var = tk.StringVar(value="Время: 00:00:00")
        self.progress_dict_var = tk.StringVar(value="Словарь: —")
        self.progress_speed_var = tk.StringVar(value="Скорость: —")
        self.progress_last_var = tk.StringVar(value="Последняя активность: —")
        self.progress_checked_var = tk.StringVar(value="Проверено: —")

        labels = [
            self.progress_scenario_var,
            self.progress_elapsed_var,
            self.progress_dict_var,
            self.progress_speed_var,
            self.progress_last_var,
            self.progress_checked_var,
        ]
        for i, var in enumerate(labels):
            tk.Label(
                stats_grid,
                textvariable=var,
                bg=BG2,
                fg=TEXT,
                font=FONT_SMALL,
                anchor="w",
            ).grid(row=i // 2, column=(i % 2) * 2, columnspan=2, sticky="ew", padx=6, pady=2)

        tk.Label(parent, text="Вывод btcrecover:", bg=BG, fg=TEXT_DIM, font=FONT_SMALL).pack(anchor="w", padx=8)
        self.run_log = scrolledtext.ScrolledText(
            parent,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            height=14,
            relief="flat",
            state="disabled",
            insertbackground=TEXT,
        )
        self.run_log.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.run_log.tag_config("found", foreground=GREEN, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self.run_log.tag_config("error", foreground=RED)
        self.run_log.tag_config("accent", foreground=ACCENT)

    # ── Вкладка Hashcat ───────────────────────────────────────────────────────
    def _build_hashcat_tab(self):
        parent = self.tab_hash

        tk.Label(
            parent,
            text="Второй этап: bitcoin2john.py извлекает hash, Hashcat пробует его по словарю. Для Bitcoin Core wallet.dat обычно mode 11300.",
            bg=BG,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=8, pady=(6, 8))

        self.hashcat_path = tk.StringVar(value="hashcat.exe" if sys.platform == "win32" else "hashcat")
        self.bitcoin2john_path = tk.StringVar(value=str(Path.cwd() / "john" / "run" / "bitcoin2john.py"))
        self.wallet_hash_path = tk.StringVar(value=str(Path.cwd() / "wallet_hash.txt"))
        self.hashcat_mode = tk.StringVar(value="11300")
        self.hashcat_workload = tk.StringVar(value="3")

        path_frame = self._section(parent, "Пути", ACCENT)
        path_frame.pack(fill="x", padx=8, pady=6)

        def path_row(label, var, command, hint):
            row = tk.Frame(path_frame, bg=BG2)
            row.pack(fill="x", padx=8, pady=5)

            tk.Label(row, text=label, bg=BG2, fg=TEXT_DIM, font=FONT_BODY, width=18, anchor="w").pack(side="left")
            tk.Entry(
                row,
                textvariable=var,
                bg=BG3,
                fg=TEXT,
                insertbackground=TEXT,
                font=FONT_BODY,
                relief="flat",
                highlightthickness=1,
                highlightcolor=ACCENT,
                highlightbackground=BORDER,
            ).pack(side="left", fill="x", expand=True, ipady=5)
            self._btn(row, "📂", command, ACCENT).pack(side="left", padx=(8, 0))

            tk.Label(path_frame, text=hint, bg=BG2, fg=TEXT_DIM, font=FONT_SMALL).pack(anchor="w", padx=30)

        path_row(
            "hashcat",
            self.hashcat_path,
            self._pick_hashcat,
            "Скачать: https://hashcat.net/hashcat/",
        )
        path_row(
            "bitcoin2john.py",
            self.bitcoin2john_path,
            self._pick_bitcoin2john,
            "Входит в John the Ripper Jumbo: https://www.openwall.com/john/",
        )
        path_row(
            "hash файл",
            self.wallet_hash_path,
            self._pick_wallet_hash_out,
            "Сюда будет сохранена строка $bitcoin$...",
        )

        options_frame = self._section(parent, "Параметры запуска", BLUE)
        options_frame.pack(fill="x", padx=8, pady=6)
        options_row = tk.Frame(options_frame, bg=BG2)
        options_row.pack(fill="x", padx=8, pady=8)

        tk.Label(options_row, text="Mode:", bg=BG2, fg=TEXT_DIM, font=FONT_BODY).pack(side="left")
        tk.Entry(options_row, textvariable=self.hashcat_mode, bg=BG3, fg=TEXT, insertbackground=TEXT, font=FONT_BODY, width=8, relief="flat").pack(side="left", padx=(6, 16), ipady=4)

        tk.Label(options_row, text="Workload -w:", bg=BG2, fg=TEXT_DIM, font=FONT_BODY).pack(side="left")
        tk.Entry(options_row, textvariable=self.hashcat_workload, bg=BG3, fg=TEXT, insertbackground=TEXT, font=FONT_BODY, width=6, relief="flat").pack(side="left", padx=(6, 16), ipady=4)

        tk.Label(options_row, text="Команда: hashcat -m 11300 -a 0 hash.txt passwords.txt", bg=BG2, fg=TEXT_DIM, font=FONT_SMALL).pack(side="left", padx=12)

        button_row = tk.Frame(parent, bg=BG)
        button_row.pack(fill="x", padx=8, pady=8)

        self.btn_extract_hash = self._btn(button_row, "🧬 Извлечь hash", self._extract_wallet_hash, ACCENT, big=True)
        self.btn_extract_hash.pack(side="left")

        self._btn(button_row, "⬇ Автоскачать Hashcat", self._download_hashcat, BLUE).pack(side="left", padx=(10, 0))
        self._btn(button_row, "⬇ Автоскачать bitcoin2john", self._download_bitcoin2john, PURPLE).pack(side="left", padx=(8, 0))

        self.btn_run_hashcat = self._btn(button_row, "⚡ Запустить Hashcat", self._start_hashcat, GREEN, big=True)
        self.btn_run_hashcat.pack(side="left", padx=10)

        self.btn_stop_hashcat = self._btn(button_row, "⏹ СТОП", self._stop_hashcat, RED, big=True)
        self.btn_stop_hashcat.pack(side="left")
        self.btn_stop_hashcat.config(state="disabled")

        self.hashcat_status_var = tk.StringVar(value="Hashcat готов. Убедись, что hashcat.exe и bitcoin2john.py выбраны правильно.")
        tk.Label(parent, textvariable=self.hashcat_status_var, bg=BG, fg=TEXT_DIM, font=FONT_SMALL).pack(anchor="w", padx=8)

        self.hashcat_log = scrolledtext.ScrolledText(
            parent,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            height=22,
            relief="flat",
            state="disabled",
            insertbackground=TEXT,
        )
        self.hashcat_log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.hashcat_log.tag_config("ok", foreground=GREEN)
        self.hashcat_log.tag_config("err", foreground=RED)
        self.hashcat_log.tag_config("info", foreground=ACCENT)

    # ── Вкладка Баланс ────────────────────────────────────────────────────────
    def _build_balance_tab(self):
        parent = self.tab_balance

        tk.Label(
            parent,
            text="Проверка баланса по адресам. Вставь адреса вручную или загрузи .txt, по одному адресу на строку.",
            bg=BG,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=8, pady=(6, 8))

        self.balance_api_base = tk.StringVar(value="https://blockstream.info/api")

        address_frame = self._section(parent, "Адреса", ACCENT)
        address_frame.pack(fill="both", expand=True, padx=8, pady=6)

        api_row = tk.Frame(address_frame, bg=BG2)
        api_row.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(api_row, text="API:", bg=BG2, fg=TEXT_DIM, font=FONT_BODY, width=10, anchor="w").pack(side="left")
        tk.Entry(
            api_row,
            textvariable=self.balance_api_base,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)

        tk.Label(
            address_frame,
            text="API по умолчанию: Blockstream Esplora. Можно заменить на свой Esplora-сервер.",
            bg=BG2,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=8)

        self.address_text = scrolledtext.ScrolledText(
            address_frame,
            bg=BG3,
            fg=TEXT,
            font=FONT_MONO,
            height=8,
            relief="flat",
            insertbackground=TEXT,
        )
        self.address_text.pack(fill="both", expand=True, padx=8, pady=6)

        button_row = tk.Frame(address_frame, bg=BG2)
        button_row.pack(fill="x", padx=8, pady=(0, 8))
        self._btn(button_row, "📂 Загрузить адреса", self._load_addresses_file, BLUE).pack(side="left")
        self._btn(button_row, "🧩 Извлечь адреса из файла", self._extract_addresses_from_file, PURPLE).pack(side="left", padx=8)
        self._btn(button_row, "🧹 Очистить", self._clear_addresses, RED).pack(side="left", padx=8)
        self.btn_check_balance = self._btn(button_row, "💰 Проверить баланс", self._check_balances, GREEN, big=True)
        self.btn_check_balance.pack(side="right")

        result_frame = self._section(parent, "Результат", GREEN)
        result_frame.pack(fill="both", expand=True, padx=8, pady=6)

        self.balance_summary_var = tk.StringVar(value="Итого: —")
        tk.Label(result_frame, textvariable=self.balance_summary_var, bg=BG2, fg=TEXT, font=FONT_HEAD).pack(anchor="w", padx=8, pady=(8, 4))

        self.balance_log = scrolledtext.ScrolledText(
            result_frame,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            height=14,
            relief="flat",
            state="disabled",
            insertbackground=TEXT,
        )
        self.balance_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.balance_log.tag_config("ok", foreground=GREEN)
        self.balance_log.tag_config("err", foreground=RED)
        self.balance_log.tag_config("info", foreground=ACCENT)

    # ── Вкладка Настройки ─────────────────────────────────────────────────────
    def _build_cfg_tab(self):
        parent = self.tab_cfg

        btr_frame = self._section(parent, "Папка btcrecover", ACCENT)
        btr_frame.pack(fill="x", padx=8, pady=(8, 4))

        btr_row = tk.Frame(btr_frame, bg=BG2)
        btr_row.pack(fill="x", padx=8, pady=6)
        tk.Entry(
            btr_row,
            textvariable=self.btr_dir,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=ACCENT,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(btr_row, "📂", self._pick_btr_dir, ACCENT).pack(side="left", padx=(8, 0))
        self.btr_dir.trace_add("write", self._sync_btr_path)

        tk.Label(
            btr_frame,
            text="Скачать btcrecover: https://github.com/3rdIteration/btcrecover",
            bg=BG2,
            fg=TEXT_DIM,
            font=FONT_SMALL,
        ).pack(anchor="w", padx=12, pady=(0, 6))

        auto_row = tk.Frame(btr_frame, bg=BG2)
        auto_row.pack(fill="x", padx=8, pady=(0, 8))
        self._btn(auto_row, "⬇ Автоскачать btcrecover", self._download_btcrecover, ACCENT).pack(side="left")

        venv_frame = self._section(parent, "Virtual Environment для btcrecover", BLUE)
        venv_frame.pack(fill="x", padx=8, pady=4)

        venv_row = tk.Frame(venv_frame, bg=BG2)
        venv_row.pack(fill="x", padx=8, pady=6)
        tk.Entry(
            venv_row,
            textvariable=self.venv_dir,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=BLUE,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(venv_row, "📂", self._pick_venv_dir, BLUE).pack(side="left", padx=(8, 0))

        self.venv_status_var = tk.StringVar(value="")
        self.venv_status_lbl = tk.Label(venv_frame, textvariable=self.venv_status_var, bg=BG2, fg=TEXT_DIM, font=FONT_SMALL)
        self.venv_status_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        venv_buttons = tk.Frame(venv_frame, bg=BG2)
        venv_buttons.pack(fill="x", padx=8, pady=(0, 8))
        self._btn(venv_buttons, "⚡ Создать venv", self._create_venv, BLUE).pack(side="left")
        self._btn(venv_buttons, "📦 Установить зависимости", self._install_deps, GREEN).pack(side="left", padx=8)
        self._btn(venv_buttons, "✓ Проверить", self._check_venv, TEXT_DIM).pack(side="left")

        work_frame = self._section(parent, "Рабочая папка", GREEN)
        work_frame.pack(fill="x", padx=8, pady=4)

        work_row = tk.Frame(work_frame, bg=BG2)
        work_row.pack(fill="x", padx=8, pady=8)
        tk.Entry(
            work_row,
            textvariable=self.work_dir,
            bg=BG3,
            fg=TEXT,
            insertbackground=TEXT,
            font=FONT_BODY,
            relief="flat",
            highlightthickness=1,
            highlightcolor=GREEN,
            highlightbackground=BORDER,
        ).pack(side="left", fill="x", expand=True, ipady=5)
        self._btn(work_row, "📂", self._pick_workdir, GREEN).pack(side="left", padx=(8, 0))

        self.cfg_log = scrolledtext.ScrolledText(
            parent,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            height=12,
            relief="flat",
            state="disabled",
            insertbackground=TEXT,
        )
        self.cfg_log.pack(fill="both", expand=True, padx=8, pady=(4, 4))
        self.cfg_log.tag_config("ok", foreground=GREEN)
        self.cfg_log.tag_config("err", foreground=RED)
        self.cfg_log.tag_config("info", foreground=ACCENT)

        self._btn(parent, "💾 Сохранить настройки", self._save_data, ACCENT).pack(pady=6)

    # ── Вкладка Где скачать ───────────────────────────────────────────────────
    def _build_help_tab(self):
        parent = self.tab_help

        text = scrolledtext.ScrolledText(
            parent,
            bg=BG2,
            fg=TEXT,
            font=FONT_MONO,
            relief="flat",
            insertbackground=TEXT,
        )
        text.pack(fill="both", expand=True, padx=8, pady=8)

        help_text = """Что нужно скачать и зачем

1. Python 3.12
   Официально:
   https://www.python.org/downloads/

   На Windows удобно проверять так:
   py -3.12 --version

   Для venv:
   py -3.12 -m venv C:\\btc_recovery\\btcrecover_venv


2. btcrecover
   GitHub:
   https://github.com/3rdIteration/btcrecover

   Пример:
   cd C:\\btc_recovery
   git clone https://github.com/3rdIteration/btcrecover


3. John the Ripper Jumbo
   Нужен из-за bitcoin2john.py, который извлекает hash из wallet.dat.

   Официально:
   https://www.openwall.com/john/

   Windows builds часто лежат на:
   https://www.openwall.com/john/k/john-*-jumbo-*-win64.zip

   После распаковки bitcoin2john.py обычно тут:
   C:\\btc_recovery\\john\\run\\bitcoin2john.py


4. bsddb3 для bitcoin2john.py
   Если bitcoin2john.py ругается:
   ModuleNotFoundError: No module named 'bsddb3'

   Поставить в venv:
   C:\\btc_recovery\\btcrecover_venv\\Scripts\\python.exe -m pip install bsddb3

   Если venv создан не на Python 3.12, лучше пересоздать:
   cd C:\\btc_recovery
   rmdir /s /q btcrecover_venv
   py -3.12 -m venv btcrecover_venv
   .\\btcrecover_venv\\Scripts\\python.exe -m pip install --upgrade pip setuptools wheel
   .\\btcrecover_venv\\Scripts\\python.exe -m pip install bsddb3


5. Hashcat
   Официально:
   https://hashcat.net/hashcat/

   Для Bitcoin Core wallet.dat обычно используется:
   hashcat.exe -m 11300 -a 0 wallet_hash.txt passwords.txt


6. Git for Windows
   Нужен, чтобы удобно скачать btcrecover через git clone:
   https://git-scm.com/download/win


7. Проверка баланса адресов
   По умолчанию используется Blockstream Esplora API:
   https://blockstream.info/api

   Вкладка Баланс НЕ извлекает адреса из wallet.dat автоматически.
   В неё нужно вставить уже известные BTC-адреса.

Рекомендуемая структура папок

C:\\btc_recovery
  wallet_recovery_gui_final.py
  wallet.dat
  passwords.txt
  wallet_hash.txt
  btcrecover\\
  btcrecover_venv\\
  john\\
    run\\
      bitcoin2john.py
  hashcat\\
    hashcat.exe


Минимальная проверка скрипта

python -m py_compile .\\wallet_recovery_gui_final.py
python .\\wallet_recovery_gui_final.py

"""
        text.insert("1.0", help_text)
        text.configure(state="disabled")

    # ── Выбор файлов ─────────────────────────────────────────────────────────
    def _pick_wallet(self):
        path = filedialog.askopenfilename(
            title="Выбери wallet.dat",
            filetypes=[("Wallet", "wallet.dat"), ("Все файлы", "*.*")],
        )
        if path:
            self.wallet_path.set(path)

    def _pick_dict(self):
        path = filedialog.askopenfilename(
            title="Выбери словарь",
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if path:
            self.dict_path.set(path)

    def _pick_out(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить словарь как",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if path:
            self.out_path.delete(0, "end")
            self.out_path.insert(0, path)

    def _pick_btr_dir(self):
        path = filedialog.askdirectory(title="Папка с btcrecover")
        if path:
            self.btr_dir.set(path)

    def _pick_venv_dir(self):
        path = filedialog.askdirectory(title="Папка для venv")
        if path:
            self.venv_dir.set(path)

    def _pick_workdir(self):
        path = filedialog.askdirectory(title="Рабочая папка")
        if path:
            self.work_dir.set(path)

    def _pick_hashcat(self):
        path = filedialog.askopenfilename(
            title="Путь к hashcat",
            filetypes=[("Executable", "*.exe"), ("Все файлы", "*.*")],
        )
        if path:
            self.hashcat_path.set(path)

    def _pick_bitcoin2john(self):
        path = filedialog.askopenfilename(
            title="Путь к bitcoin2john.py",
            filetypes=[("Python", "*.py"), ("Все файлы", "*.*")],
        )
        if path:
            self.bitcoin2john_path.set(path)

    def _pick_wallet_hash_out(self):
        path = filedialog.asksaveasfilename(
            title="Сохранить hash как",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if path:
            self.wallet_hash_path.set(path)

    def _download_file(self, url: str, dst: Path):
        req = urllib.request.Request(url, headers={"User-Agent": "wallet-recovery-gui/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(dst, "wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)

    def _download_btcrecover(self):
        target = Path(self.btr_dir.get().strip())
        if not target:
            messagebox.showerror("Ошибка", "Укажи папку btcrecover.")
            return
        self._log_cfg("Старт автоскачивания btcrecover...", "info")
        threading.Thread(target=self._download_btcrecover_worker, args=(target,), daemon=True).start()

    def _download_btcrecover_worker(self, target: Path):
        try:
            archive_url = "https://github.com/3rdIteration/btcrecover/archive/refs/heads/master.zip"
            work_dir = target.parent
            work_dir.mkdir(parents=True, exist_ok=True)
            archive_path = work_dir / "btcrecover_master.zip"

            self.after(0, self._log_cfg, f"Скачиваю: {archive_url}", "info")
            self._download_file(archive_url, archive_path)
            self.after(0, self._log_cfg, f"Архив сохранен: {archive_path}", "ok")

            extract_root = work_dir / "_btcrecover_extract"
            if extract_root.exists():
                import shutil
                shutil.rmtree(extract_root)
            extract_root.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_root)

            src_dir = extract_root / "btcrecover-master"
            if not src_dir.exists():
                raise RuntimeError("Не найден каталог btcrecover-master после распаковки")

            if target.exists():
                import shutil
                backup = target.with_name(target.name + "_backup")
                if backup.exists():
                    shutil.rmtree(backup)
                target.rename(backup)
                self.after(0, self._log_cfg, f"Старая папка перенесена в backup: {backup}", "info")

            src_dir.rename(target)
            self.after(0, self._log_cfg, f"✓ btcrecover установлен: {target}", "ok")
            self.after(0, self._sync_btr_path)
            self.after(0, self._check_venv)
        except Exception as exc:
            self.after(0, self._log_cfg, f"✗ Автоскачивание btcrecover не удалось: {exc}", "err")

    def _download_hashcat(self):
        self._log_hashcat("Старт автоскачивания Hashcat...", "info")
        threading.Thread(target=self._download_hashcat_worker, daemon=True).start()

    def _download_hashcat_worker(self):
        try:
            if sys.platform != "win32":
                raise RuntimeError("Автоскачивание Hashcat сейчас реализовано только для Windows (скачивается .7z архив).")

            url = "https://hashcat.net/files/hashcat-6.2.6.7z"
            base_dir = Path(self.work_dir.get().strip() or Path.cwd())
            hashcat_dir = base_dir / "hashcat"
            archive_path = base_dir / "hashcat-6.2.6.7z"

            self.after(0, self._log_hashcat, f"Скачиваю: {url}", "info")
            self._download_file(url, archive_path)
            self.after(0, self._log_hashcat, f"Архив сохранён: {archive_path}", "ok")
            self.after(0, self._log_hashcat, "Распакуй .7z (7-Zip) в папку hashcat и выбери hashcat.exe через кнопку 📂.", "info")

            guessed = hashcat_dir / "hashcat.exe"
            if guessed.exists():
                self.after(0, self.hashcat_path.set, str(guessed))
                self.after(0, self._log_hashcat, f"✓ Найден hashcat.exe: {guessed}", "ok")
        except Exception as exc:
            self.after(0, self._log_hashcat, f"✗ Автоскачивание Hashcat не удалось: {exc}", "err")

    def _download_bitcoin2john(self):
        self._log_hashcat("Старт автоскачивания John Jumbo (для bitcoin2john.py)...", "info")
        threading.Thread(target=self._download_bitcoin2john_worker, daemon=True).start()

    def _download_bitcoin2john_worker(self):
        try:
            url = "https://github.com/openwall/john/archive/refs/heads/bleeding-jumbo.zip"
            base_dir = Path(self.work_dir.get().strip() or Path.cwd())
            archive_path = base_dir / "john-bleeding-jumbo.zip"
            extract_root = base_dir / "_john_extract"
            john_target = base_dir / "john"

            self.after(0, self._log_hashcat, f"Скачиваю: {url}", "info")
            self._download_file(url, archive_path)
            self.after(0, self._log_hashcat, f"Архив сохранён: {archive_path}", "ok")

            if extract_root.exists():
                import shutil
                shutil.rmtree(extract_root)
            extract_root.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_root)

            src_dir = extract_root / "john-bleeding-jumbo"
            if not src_dir.exists():
                raise RuntimeError("Не найден каталог john-bleeding-jumbo после распаковки")

            if john_target.exists():
                import shutil
                backup = john_target.with_name("john_backup")
                if backup.exists():
                    shutil.rmtree(backup)
                john_target.rename(backup)
                self.after(0, self._log_hashcat, f"Старая папка john перенесена в backup: {backup}", "info")

            src_dir.rename(john_target)
            b2j = john_target / "run" / "bitcoin2john.py"
            if not b2j.exists():
                raise RuntimeError("bitcoin2john.py не найден в john/run после установки")

            self.after(0, self.bitcoin2john_path.set, str(b2j))
            self.after(0, self._log_hashcat, f"✓ bitcoin2john.py установлен: {b2j}", "ok")
            self.after(0, lambda: self.hashcat_status_var.set("bitcoin2john.py установлен"))
        except Exception as exc:
            self.after(0, self._log_hashcat, f"✗ Автоскачивание bitcoin2john не удалось: {exc}", "err")

    # ── Сохранение / загрузка ─────────────────────────────────────────────────
    def _collect_data(self):
        return {
            "words": self.lst_words.get(),
            "phrases": self.lst_phrases.get(),
            "numbers": self.lst_numbers.get(),
            "specials": self.lst_specials.get(),
            "templates": self.lst_templates.get(),
            "wallet_path": self.wallet_path.get(),
            "dict_path": self.dict_path.get(),
            "out_path": self.out_path.get(),
            "btr_dir": self.btr_dir.get(),
            "venv_dir": self.venv_dir.get(),
            "btcrecover": self.btcrecover_path.get(),
            "work_dir": self.work_dir.get(),
            "caps": self.var_caps.get(),
            "ru2en": self.var_ru2en.get(),
            "reverse": self.var_reverse.get(),
            "swapcase": self.var_swapcase.get(),
            "altcase": self.var_altcase.get(),
            "altcase_inv": self.var_altcase_inv.get(),
            "use_empty_num": self.var_use_empty_num.get(),
            "use_empty_spec": self.var_use_empty_spec.get(),
            "run_plain": self.var_run_plain.get(),
            "run_typos1": self.var_run_typos1.get(),
            "run_typos2": self.var_run_typos2.get(),
            "run_capslock": self.var_run_capslock.get(),
            "hashcat_path": self.hashcat_path.get(),
            "bitcoin2john_path": self.bitcoin2john_path.get(),
            "wallet_hash_path": self.wallet_hash_path.get(),
            "hashcat_mode": self.hashcat_mode.get(),
            "hashcat_workload": self.hashcat_workload.get(),
            "balance_api_base": self.balance_api_base.get(),
            "addresses_text": self.address_text.get("1.0", "end").strip(),
        }

    def _save_data_to_disk(self):
        data = self._collect_data()
        bak_file = DATA_FILE.with_suffix(".bak")
        tmp_file = DATA_FILE.with_suffix(".tmp")
        if DATA_FILE.exists():
            try:
                DATA_FILE.replace(bak_file)
            except Exception:
                pass
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_file.replace(DATA_FILE)

    def _save_data(self):
        try:
            self._save_data_to_disk()
            messagebox.showinfo("Сохранено", f"Данные сохранены:\n{DATA_FILE}")
        except Exception as exc:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить настройки:\n\n{exc}")

    def _save_data_silent(self):
        try:
            self._save_data_to_disk()
        except Exception as exc:
            print(f"Ошибка автосохранения {DATA_FILE}: {exc}")

    def _start_autosave(self):
        self._autosave_tick()

    def _autosave_tick(self):
        self._save_data_silent()
        self._autosave_job = self.after(15000, self._autosave_tick)

    def _on_close(self):
        if self._autosave_job is not None:
            try:
                self.after_cancel(self._autosave_job)
            except Exception:
                pass
            self._autosave_job = None
        self._save_data_silent()
        self.destroy()

    def _load_data(self):
        candidates = [DATA_FILE, DATA_FILE.with_suffix(".bak"), DATA_FILE.with_suffix(".tmp")]
        source_file = None
        for candidate in candidates:
            if candidate.exists():
                source_file = candidate
                break

        if source_file is None:
            return

        try:
            with open(source_file, encoding="utf-8") as f:
                data = json.load(f)

            self.lst_words.set(data.get("words", []))
            self.lst_phrases.set(data.get("phrases", []))
            self.lst_numbers.set(data.get("numbers", []))
            self.lst_specials.set(data.get("specials", []))
            self.lst_templates.set(data.get("templates", DEFAULT_TEMPLATES))

            self.wallet_path.set(data.get("wallet_path", ""))
            self.dict_path.set(data.get("dict_path", "passwords.txt"))

            if data.get("out_path"):
                self.out_path.delete(0, "end")
                self.out_path.insert(0, data["out_path"])

            if data.get("btr_dir"):
                self.btr_dir.set(data["btr_dir"])
            if data.get("venv_dir"):
                self.venv_dir.set(data["venv_dir"])
            if data.get("btcrecover"):
                self.btcrecover_path.set(data["btcrecover"])
            if data.get("work_dir"):
                self.work_dir.set(data["work_dir"])

            self.var_caps.set(data.get("caps", True))
            self.var_ru2en.set(data.get("ru2en", True))
            self.var_reverse.set(data.get("reverse", False))
            self.var_swapcase.set(data.get("swapcase", True))
            self.var_altcase.set(data.get("altcase", True))
            self.var_altcase_inv.set(data.get("altcase_inv", True))
            self.var_use_empty_num.set(data.get("use_empty_num", True))
            self.var_use_empty_spec.set(data.get("use_empty_spec", True))

            self.var_run_plain.set(data.get("run_plain", True))
            self.var_run_typos1.set(data.get("run_typos1", True))
            self.var_run_typos2.set(data.get("run_typos2", True))
            self.var_run_capslock.set(data.get("run_capslock", True))

            self.hashcat_path.set(data.get("hashcat_path", self.hashcat_path.get()))
            self.bitcoin2john_path.set(data.get("bitcoin2john_path", self.bitcoin2john_path.get()))
            self.wallet_hash_path.set(data.get("wallet_hash_path", self.wallet_hash_path.get()))
            self.hashcat_mode.set(data.get("hashcat_mode", "11300"))
            self.hashcat_workload.set(data.get("hashcat_workload", "3"))

            self.balance_api_base.set(data.get("balance_api_base", self.balance_api_base.get()))
            if data.get("addresses_text"):
                self.address_text.delete("1.0", "end")
                self.address_text.insert("1.0", data.get("addresses_text", ""))
        except Exception as exc:
            print(f"Ошибка загрузки {source_file}: {exc}")

    def _clear_all(self):
        if messagebox.askyesno("Очистить", "Очистить все слова, фразы, цифры и спецсимволы?"):
            self.lst_words.set([])
            self.lst_phrases.set([])
            self.lst_numbers.set([])
            self.lst_specials.set([])

    # ── Логи ──────────────────────────────────────────────────────────────────
    def _log_text(self, widget, msg, tag=None):
        widget.configure(state="normal")
        if tag:
            widget.insert("end", msg + "\n", tag)
        else:
            widget.insert("end", msg + "\n")
        widget.configure(state="disabled")
        widget.see("end")

    def _log_gen(self, msg):
        self._log_text(self.gen_log, msg)

    def _log_run(self, msg, tag=None):
        self._log_text(self.run_log, msg, tag)

    def _log_cfg(self, msg, tag=None):
        self._log_text(self.cfg_log, msg, tag)

    def _log_hashcat(self, msg, tag=None):
        self._log_text(self.hashcat_log, msg, tag)

    def _log_balance(self, msg, tag=None):
        self._log_text(self.balance_log, msg, tag)

    # ── venv ──────────────────────────────────────────────────────────────────
    def _sync_btr_path(self, *_):
        self.btcrecover_path.set(str(Path(self.btr_dir.get()) / "btcrecover.py"))

    def _venv_python(self):
        venv_dir = Path(self.venv_dir.get())
        if sys.platform == "win32":
            return venv_dir / "Scripts" / "python.exe"
        return venv_dir / "bin" / "python"

    def _check_venv(self):
        py = self._venv_python()
        btr = Path(self.btcrecover_path.get())
        ok_venv = py.exists()
        ok_btr = btr.exists()

        py_ver = _get_python_version(py) if ok_venv else None
        ok_py312 = bool(py_ver and py_ver.startswith("3.12."))

        if ok_venv and ok_btr and ok_py312:
            self.venv_status_var.set("✓ venv готов (Python 3.12), btcrecover найден")
            self.venv_status_lbl.config(fg=GREEN)
        elif ok_venv and not ok_py312:
            self.venv_status_var.set("✗ venv есть, но Python не 3.12")
            self.venv_status_lbl.config(fg=RED)
        elif ok_venv:
            self.venv_status_var.set("⚠ venv есть, но btcrecover.py не найден")
            self.venv_status_lbl.config(fg=ACCENT)
        else:
            self.venv_status_var.set("✗ venv не создан")
            self.venv_status_lbl.config(fg=RED)

        py_status = f"✓ {py}" if ok_venv else "✗ не найден"
        if ok_venv:
            py_status += f" (версия: {py_ver or 'не определена'})"
        self._log_cfg(f"Python venv : {py_status}", "ok" if ok_venv and ok_py312 else "err")
        self._log_cfg(f"btcrecover  : {'✓ ' + str(btr) if ok_btr else '✗ не найден'}", "ok" if ok_btr else "err")

    def _create_venv(self):
        target = self.venv_dir.get().strip()
        if not target:
            messagebox.showerror("Ошибка", "Укажи папку venv.")
            return
        self._log_cfg(f"Создаю venv: {target}", "info")
        threading.Thread(target=self._create_venv_worker, args=(target,), daemon=True).start()

    def _create_venv_worker(self, target):
        try:
            target_path = Path(target)
            if sys.platform == "win32":
                cmd = ["py", "-3.12", "-m", "venv", str(target_path)]
                self.after(0, self._log_cfg, "Пробую создать venv через Python Launcher: py -3.12", "info")

                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                if proc.stdout:
                    for line in proc.stdout:
                        line = line.rstrip()
                        if line:
                            self.after(0, self._log_cfg, line)
                proc.wait()

                if proc.returncode != 0:
                    raise RuntimeError("Не удалось создать venv через py -3.12. Убедись, что Python 3.12 установлен и доступен в py launcher.")
            else:
                if not _is_python_312(Path(sys.executable)):
                    raise RuntimeError("Текущий интерпретатор не Python 3.12. Запусти GUI под Python 3.12.")
                venv_mod.create(target, with_pip=True, clear=True)

            py = target_path / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            self.after(0, self._log_cfg, "Устанавливаю bsddb3 в новый venv (для bitcoin2john)...", "info")
            pip_cmd = [str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "bsddb3"]
            pip_proc = subprocess.Popen(pip_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            if pip_proc.stdout:
                for line in pip_proc.stdout:
                    line = line.rstrip()
                    if line:
                        self.after(0, self._log_cfg, line)
            pip_proc.wait()
            if pip_proc.returncode != 0:
                raise RuntimeError("venv создан, но не удалось установить bsddb3. Установи вручную: python -m pip install bsddb3")

            self.after(0, self._log_cfg, "✓ venv создан (Python 3.12), bsddb3 установлен", "ok")
            self.after(0, self._check_venv)
        except Exception as exc:
            self.after(0, self._log_cfg, f"✗ Ошибка создания venv: {exc}", "err")

    def _install_deps(self):
        py = self._venv_python()
        req = Path(self.btr_dir.get()) / "requirements.txt"

        if not py.exists():
            messagebox.showerror("Ошибка", "Сначала создай venv.")
            return
        if not req.exists():
            messagebox.showerror(
                "Ошибка",
                f"requirements.txt не найден:\n{req}\n\nСначала клонируй btcrecover в указанную папку.",
            )
            return

        if not _is_python_312(py):
            messagebox.showerror("Ошибка", "Этот инструмент поддерживает только venv на Python 3.12. Пересоздай venv через py -3.12 -m venv ...")
            return

        cmd = [str(py), "-m", "pip", "install", "-r", str(req), "bsddb3"]
        self._log_cfg("Устанавливаю зависимости btcrecover + bsddb3...", "info")
        threading.Thread(target=self._install_deps_worker, args=(cmd,), daemon=True).start()

    def _install_deps_worker(self, cmd):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            if proc.stdout:
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        self.after(0, self._log_cfg, line)
            proc.wait()
            if proc.returncode == 0:
                self.after(0, self._log_cfg, "✓ Зависимости установлены", "ok")
                self.after(0, self._check_venv)
            else:
                self.after(0, self._log_cfg, f"✗ pip завершился с кодом {proc.returncode}", "err")
        except Exception as exc:
            self.after(0, self._log_cfg, f"✗ Ошибка установки зависимостей: {exc}", "err")

    # ── Генерация словаря ─────────────────────────────────────────────────────
    def _reset_templates(self):
        self.lst_templates.set(DEFAULT_TEMPLATES)

    def _expand_word_like(self, raw_items, is_phrase=False):
        result = []

        def add_variants(value):
            value = value.strip()
            if not value:
                return

            candidates = [value]

            if self.var_caps.get():
                candidates += [value.lower(), value.upper(), value.capitalize()]

            if self.var_swapcase.get():
                candidates.append(value.swapcase())

            if self.var_altcase.get():
                candidates.append(alt_case(value))

            if self.var_altcase_inv.get():
                candidates.append(alt_case_inverse(value))

            if self.var_reverse.get():
                candidates.append(value[::-1])

            if self.var_ru2en.get():
                converted = ru_to_en(value)
                if converted != value:
                    candidates.append(converted)
                    if self.var_caps.get():
                        candidates += [converted.lower(), converted.upper(), converted.capitalize()]
                    if self.var_swapcase.get():
                        candidates.append(converted.swapcase())
                    if self.var_altcase.get():
                        candidates.append(alt_case(converted))
                    if self.var_altcase_inv.get():
                        candidates.append(alt_case_inverse(converted))
                    if self.var_reverse.get():
                        candidates.append(converted[::-1])

            result.extend(candidates)

        for item in raw_items:
            item = item.strip()
            if not item:
                continue

            if is_phrase:
                parts = item.split()
                add_variants("".join(parts))
                add_variants("_".join(parts))
            else:
                add_variants(item)

        return unique_keep_order(result)

    def _template_valid(self, template):
        cleaned = template
        for token in TOKENS:
            cleaned = cleaned.replace(token, "")
        return bool(template.strip()) and any(token in template for token in TOKENS) and "{" not in cleaned and "}" not in cleaned

    def _prepare_generation(self):
        words = self._expand_word_like(self.lst_words.get(), is_phrase=False)
        phrases = self._expand_word_like(self.lst_phrases.get(), is_phrase=True)
        numbers = unique_keep_order(self.lst_numbers.get())
        specials = unique_keep_order(self.lst_specials.get())
        templates = [tpl for tpl in unique_keep_order(self.lst_templates.get()) if self._template_valid(tpl)]

        if self.var_use_empty_num.get():
            numbers = [""] + numbers
        if self.var_use_empty_spec.get():
            specials = [""] + specials

        pools = {
            "{W}": words,
            "{P}": phrases,
            "{N}": numbers,
            "{S}": specials,
        }
        return pools, templates

    def _estimate_count(self, pools, templates):
        total = 0
        per_template = []

        for tpl in templates:
            count = 1
            used_any = False

            for token, values in pools.items():
                token_count = tpl.count(token)
                if token_count:
                    used_any = True
                    count *= len(values) ** token_count

            if not used_any:
                count = 0

            per_template.append((tpl, count))
            total += count

        return total, per_template

    def _estimate_dialog(self):
        pools, templates = self._prepare_generation()
        total, per_template = self._estimate_count(pools, templates)

        text = [
            f"Слова W: {len(pools['{W}']):,}",
            f"Фразы P: {len(pools['{P}']):,}",
            f"Цифры N: {len(pools['{N}']):,}",
            f"Символы S: {len(pools['{S}']):,}",
            "",
            "По шаблонам:",
        ]

        for tpl, count in per_template:
            text.append(f"{tpl}: {count:,}")

        text += ["", f"Итого до удаления дублей: {total:,}"]
        messagebox.showinfo("Оценка словаря", "\n".join(text))

    def _generate(self):
        if self._generating:
            return

        pools, templates = self._prepare_generation()
        if not templates:
            messagebox.showerror("Ошибка", "Нет валидных шаблонов. Пример: {W}{N}{S}")
            return

        if not pools["{W}"] and not pools["{P}"]:
            messagebox.showerror("Ошибка", "Добавь хотя бы слова или фразы.")
            return

        total, _ = self._estimate_count(pools, templates)
        if total == 0:
            messagebox.showerror("Ошибка", "По текущим шаблонам нечего генерировать.")
            return

        if total > DEFAULT_WARNING_LIMIT:
            ok = messagebox.askyesno(
                "Большой словарь",
                f"Оценка до удаления дублей: {total:,} строк.\n\n"
                "Это может занять много времени и места на диске.\n"
                "Продолжить?",
            )
            if not ok:
                return

        self.gen_log.configure(state="normal")
        self.gen_log.delete("1.0", "end")
        self.gen_log.configure(state="disabled")

        out = self.out_path.get().strip() or "passwords.txt"
        self.btn_generate.config(state="disabled")
        self._generating = True
        threading.Thread(target=self._generate_worker, args=(pools, templates, out, total), daemon=True).start()

    def _template_to_ordered_tokens(self, template):
        ordered = []
        tmp = template
        scan = template
        idx = 0

        while True:
            found = [(scan.find(token), token) for token in TOKENS if scan.find(token) != -1]
            if not found:
                break

            pos, token = min(found, key=lambda x: x[0])
            marker = f"__T{idx}__"
            ordered.append((marker, token))
            tmp = tmp.replace(token, marker, 1)
            scan = scan[:pos] + " " * len(token) + scan[pos + len(token):]
            idx += 1

        return tmp, ordered

    def _generate_worker(self, pools, templates, out, estimated):
        def log(msg):
            self.after(0, self._log_gen, msg)

        log("── Начинаю генерацию ──────────────────────")
        log(f"Шаблонов: {len(templates)}")
        log(f"Оценка до удаления дублей: {estimated:,}")
        log(f"Файл: {out}")

        seen = set()
        count = 0

        try:
            with open(out, "w", encoding="utf-8", newline="\n") as fout:
                for tpl in templates:
                    tmp_tpl, ordered = self._template_to_ordered_tokens(tpl)
                    if not ordered:
                        continue

                    log(f"Шаблон: {tpl}")

                    def walk(i, chosen):
                        nonlocal count

                        if i >= len(ordered):
                            pwd = tmp_tpl
                            for marker, value in chosen.items():
                                pwd = pwd.replace(marker, value)

                            if pwd and pwd not in seen:
                                seen.add(pwd)
                                fout.write(pwd + "\n")
                                count += 1

                                if count % PROGRESS_EVERY == 0:
                                    log(f"Записано: {count:,}")
                            return

                        marker, token = ordered[i]
                        values = pools[token]
                        if not values:
                            return

                        for value in values:
                            chosen[marker] = value
                            walk(i + 1, chosen)
                            chosen.pop(marker, None)

                    walk(0, {})

            log("")
            log(f"✓ Готово. Уникальных паролей: {count:,}")
            log(f"Файл: {out}")
            self.after(0, lambda: self.dict_path.set(out))
        except Exception as exc:
            log(f"✗ Ошибка генерации: {exc}")
        finally:
            self._generating = False
            self.after(0, lambda: self.btn_generate.config(state="normal"))

    # ── Мониторинг запуска btcrecover ─────────────────────────────────────────
    def _format_duration(self, seconds):
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        sec = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"

    def _count_file_lines(self, path):
        count = 0
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                count += block.count(bytes([10]))
        return count

    def _reset_progress_ui(self, dict_lines=0):
        self._run_started_at = time.time()
        self._scenario_started_at = None
        self._last_output_at = None
        self._dict_line_count = dict_lines
        self._current_scenario = "—"
        self._last_speed = "—"
        self._last_checked_password = "—"

        self.progress_scenario_var.set("Сценарий: —")
        self.progress_elapsed_var.set("Время: 00:00:00")
        self.progress_dict_var.set(f"Словарь: {dict_lines:,} строк" if dict_lines else "Словарь: —")
        self.progress_speed_var.set("Скорость: —")
        self.progress_last_var.set("Последняя активность: —")
        self.progress_checked_var.set("Проверено: —")

    def _start_progress_timer(self):
        self._update_progress_timer()

    def _update_progress_timer(self):
        if not self._running or not self._run_started_at:
            return

        now = time.time()
        elapsed = now - self._run_started_at

        self.progress_elapsed_var.set(f"Время: {self._format_duration(elapsed)}")
        self.progress_scenario_var.set(f"Сценарий: {self._current_scenario}")
        self.progress_speed_var.set(f"Скорость: {self._last_speed}")
        checked_value = self._parse_checked_count()
        if checked_value is not None and self._dict_line_count > 0:
            pct = min(100.0, (checked_value / self._dict_line_count) * 100.0)
            self.progress_checked_var.set(
                f"Проверено: {self._last_checked_password} (~{pct:.2f}% текущего словаря)"
            )
        else:
            self.progress_checked_var.set(f"Проверено: {self._last_checked_password}")

        if self._last_output_at:
            silent = int(now - self._last_output_at)
            self.progress_last_var.set(f"Последняя активность: {silent} сек назад")
        else:
            self.progress_last_var.set("Последняя активность: ждём вывод")

        self.after(1000, self._update_progress_timer)

    def _parse_btcrecover_progress(self, line):
        self._last_output_at = time.time()
        low = line.lower()

        speed_patterns = [
            r"([0-9][0-9,. ]*) *(?:passwords|pass|pwd|p) */ *(?:sec|s|second)",
            r"([0-9][0-9,. ]*) *(?:passwords|pass|pwd) *(?:per|/) *(?:minute|min)",
            r"([0-9][0-9,. ]*) *p/s",
        ]
        for pat in speed_patterns:
            m = re.search(pat, low)
            if m:
                self._last_speed = m.group(1).strip() + " паролей/сек"
                break

        checked_patterns = [
            r"password *# *([0-9][0-9,. ]*)",
            r"after finishing password *# *([0-9][0-9,. ]*)",
            r"([0-9][0-9,. ]*) *passwords",
        ]
        for pat in checked_patterns:
            m = re.search(pat, low)
            if m:
                self._last_checked_password = m.group(1).strip()
                break

    def _parse_checked_count(self):
        raw = (self._last_checked_password or "").strip()
        if not raw or raw == "—":
            return None
        cleaned = raw.replace(" ", "").replace(",", "").replace(".", "")
        return int(cleaned) if cleaned.isdigit() else None

    # ── btcrecover ────────────────────────────────────────────────────────────
    def _build_run_plan(self, py, btr, wallet, dct):
        base = [str(py), btr, "--wallet", wallet, "--passwordlist", dct]
        typo_types = ["--typos-case", "--typos-delete", "--typos-repeat", "--typos-swap"]

        runs = []
        if self.var_run_plain.get():
            runs.append(("Просто словарь", base[:]))
        if self.var_run_typos1.get():
            runs.append(("Typos 1", base + ["--typos", "1"] + typo_types))
        if self.var_run_typos2.get():
            runs.append(("Typos 2", base + ["--typos", "2"] + typo_types))
        if self.var_run_capslock.get():
            runs.append(("CapsLock", base + ["--typos", "1", "--typos-capslock"]))

        return runs

    def _start_btcrecover(self):
        wallet = self.wallet_path.get().strip()
        dct = self.dict_path.get().strip()
        btr = self.btcrecover_path.get().strip()
        py = self._venv_python()

        if not _is_python_312(py):
            messagebox.showerror("Ошибка", "Для запуска нужен Python 3.12 в venv. Пересоздай venv через py -3.12 -m venv ...")
            return

        if not wallet or not Path(wallet).exists():
            messagebox.showerror("Ошибка", f"wallet.dat не найден:\n{wallet}")
            return
        if not dct or not Path(dct).exists():
            messagebox.showerror("Ошибка", f"Словарь не найден:\n{dct}")
            return
        if not btr or not Path(btr).exists():
            messagebox.showerror("Ошибка", f"btcrecover.py не найден:\n{btr}")
            return
        if not py.exists():
            messagebox.showerror("Ошибка", f"Python из venv не найден:\n{py}\n\nСоздай venv и установи зависимости.")
            return

        work_dir = self.work_dir.get().strip() or str(Path.cwd())
        if not Path(work_dir).exists():
            messagebox.showerror("Ошибка", f"Рабочая папка не найдена:\n{work_dir}")
            return

        runs = self._build_run_plan(py, btr, wallet, dct)
        if not runs:
            messagebox.showerror("Ошибка", "Выбери хотя бы один сценарий запуска.")
            return

        try:
            dict_lines = self._count_file_lines(dct)
        except Exception:
            dict_lines = 0

        self._reset_progress_ui(dict_lines)

        self.run_log.configure(state="normal")
        self.run_log.delete("1.0", "end")
        self.run_log.configure(state="disabled")

        self._log_run("Очередь запусков через venv:", "accent")
        for idx, (name, cmd) in enumerate(runs, start=1):
            self._log_run(f"{idx}. {name}: {' '.join(cmd)}", "accent")
        self._log_run("─" * 70)

        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_var.set("Выполняется очередь перебора...")
        self.status_lbl.config(fg=ACCENT)
        self._running = True
        self._stop_requested = False
        self._start_progress_timer()

        threading.Thread(target=self._run_queue_worker, args=(runs, work_dir), daemon=True).start()

    def _run_queue_worker(self, runs, work_dir):
        try:
            for idx, (name, cmd) in enumerate(runs, start=1):
                if self._stop_requested:
                    break

                self._current_scenario = name
                self._scenario_started_at = time.time()
                self._last_output_at = time.time()
                self._last_speed = "—"
                self._last_checked_password = "—"

                self.after(0, self._log_run, "")
                self.after(0, self._log_run, f"▶ Запуск {idx}/{len(runs)}: {name}", "accent")
                self.after(0, lambda n=name: self.status_var.set(f"Выполняется: {n}"))

                rc = self._run_single_btcrecover(cmd, work_dir)

                if self._stop_requested:
                    self.after(0, self._log_run, "Очередь остановлена пользователем.", "error")
                    break

                if rc == 0:
                    self.after(0, self._log_run, f"✓ Сценарий завершён: {name}", "found")
                else:
                    self.after(0, self._log_run, f"Сценарий завершён с кодом {rc}: {name}", "error")

            if not self._stop_requested:
                self.after(0, self._log_run, "\n✓ Очередь запусков завершена.", "found")
                self.after(0, lambda: self.status_var.set("✓ Очередь завершена"))
                self.after(0, lambda: self.status_lbl.config(fg=GREEN))
        except Exception as exc:
            self.after(0, self._log_run, f"Ошибка очереди запусков: {exc}", "error")
            self.after(0, lambda: self.status_var.set("Ошибка запуска"))
            self.after(0, lambda: self.status_lbl.config(fg=RED))
        finally:
            self.proc = None
            self._running = False
            self._stop_requested = False
            self.after(0, lambda: self.btn_start.config(state="normal"))
            self.after(0, lambda: self.btn_stop.config(state="disabled"))

    def _run_single_btcrecover(self, cmd, work_dir):
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=work_dir,
        )

        def handle_output(raw_line):
            line = raw_line.rstrip()
            if not line:
                return

            low = line.lower()
            tag = None

            self._parse_btcrecover_progress(line)

            if "password found" in low or "пароль найден" in low:
                tag = "found"
            elif "error" in low or "ошибка" in low or "traceback" in low:
                tag = "error"

            self.after(0, self._log_run, line, tag)

        if self.proc.stdout:
            buffer = ""
            while True:
                if self._stop_requested:
                    break

                ch = self.proc.stdout.read(1)
                if ch == "" and self.proc.poll() is not None:
                    break
                if ch == "":
                    continue

                if ch in ("\n", "\r"):
                    if buffer:
                        handle_output(buffer)
                        buffer = ""
                    continue

                buffer += ch

            if buffer:
                handle_output(buffer)

        if self._stop_requested and self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

        self.proc.wait()
        rc = self.proc.returncode
        self.proc = None
        return rc

    def _stop_btcrecover(self):
        if self._running:
            self._stop_requested = True
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self._log_run("⏹ Остановлено пользователем.", "error")
            self.status_var.set("Остановлено")
            self.status_lbl.config(fg=RED)

    # ── Hashcat ───────────────────────────────────────────────────────────────
    def _extract_wallet_hash(self):
        wallet = self.wallet_path.get().strip()
        b2j = self.bitcoin2john_path.get().strip()
        out = self.wallet_hash_path.get().strip()
        py = self._venv_python() if self._venv_python().exists() else Path(sys.executable)

        if not _is_python_312(py):
            messagebox.showerror("Ошибка", "Для запуска нужен Python 3.12 в venv. Пересоздай venv через py -3.12 -m venv ...")
            return

        if not wallet or not Path(wallet).exists():
            messagebox.showerror("Ошибка", f"wallet.dat не найден:\n{wallet}")
            return
        if not b2j or not Path(b2j).exists():
            messagebox.showerror("Ошибка", f"bitcoin2john.py не найден:\n{b2j}")
            return
        if not out:
            messagebox.showerror("Ошибка", "Укажи файл для сохранения hash.")
            return

        self.hashcat_log.configure(state="normal")
        self.hashcat_log.delete("1.0", "end")
        self.hashcat_log.configure(state="disabled")

        wallet_copy = self._prepare_safe_wallet_copy(Path(wallet))
        if wallet_copy is None:
            self.hashcat_status_var.set("Не удалось подготовить копию wallet.dat")
            return

        cmd = [str(py), b2j, str(wallet_copy)]
        self._log_hashcat("Извлекаю hash через bitcoin2john.py:", "info")
        self._log_hashcat(f"Использую безопасную копию wallet.dat: {wallet_copy}", "info")
        self._log_hashcat(" ".join(cmd), "info")
        self.btn_extract_hash.config(state="disabled")
        self.hashcat_status_var.set("Извлекаю hash...")

        threading.Thread(target=self._extract_wallet_hash_worker, args=(cmd, out), daemon=True).start()

    def _prepare_safe_wallet_copy(self, wallet_path: Path):
        try:
            import shutil
            ts = time.strftime("%Y%m%d_%H%M%S")
            copies_dir = Path(self.work_dir.get().strip() or Path.cwd()) / "safe_wallet_copies"
            copies_dir.mkdir(parents=True, exist_ok=True)
            dst = copies_dir / f"{wallet_path.stem}_{ts}{wallet_path.suffix}"
            shutil.copy2(wallet_path, dst)
            return dst
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось создать безопасную копию wallet.dat:\n{exc}")
            return None

    def _extract_wallet_hash_worker(self, cmd, out):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            lines = []

            if proc.stdout:
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        lines.append(line)
                        self.after(0, self._log_hashcat, line)

            proc.wait()

            bitcoin_hash = None
            for line in lines:
                if "$bitcoin$" in line:
                    bitcoin_hash = line[line.find("$bitcoin$"):].strip()
                    break

            if proc.returncode != 0 and not bitcoin_hash:
                self.after(0, self._log_hashcat, f"bitcoin2john завершился с кодом {proc.returncode}", "err")
                self.after(0, lambda: self.hashcat_status_var.set("Ошибка извлечения hash"))
                return

            if not bitcoin_hash:
                self.after(0, self._log_hashcat, "Не нашёл строку $bitcoin$ в выводе bitcoin2john.py", "err")
                self.after(0, lambda: self.hashcat_status_var.set("Hash не найден"))
                return

            out_path = Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            with open(out_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(bitcoin_hash + "\n")

            self.after(0, self._log_hashcat, f"✓ Hash сохранён: {out_path}", "ok")
            self.after(0, lambda: self.hashcat_status_var.set("Hash извлечён"))
        except Exception as exc:
            self.after(0, self._log_hashcat, f"Ошибка извлечения hash: {exc}", "err")
            self.after(0, lambda: self.hashcat_status_var.set("Ошибка извлечения hash"))
        finally:
            self.after(0, lambda: self.btn_extract_hash.config(state="normal"))

    def _start_hashcat(self):
        hashcat = self.hashcat_path.get().strip()
        hash_file = self.wallet_hash_path.get().strip()
        dct = self.dict_path.get().strip()
        mode = self.hashcat_mode.get().strip() or "11300"
        workload = self.hashcat_workload.get().strip() or "3"

        if sys.platform == "win32" and not Path(hashcat).exists() and hashcat.lower() != "hashcat.exe":
            messagebox.showerror("Ошибка", f"hashcat.exe не найден:\n{hashcat}")
            return
        if not hash_file or not Path(hash_file).exists():
            messagebox.showerror("Ошибка", f"Hash файл не найден:\n{hash_file}\n\nСначала нажми 'Извлечь hash'.")
            return
        if not dct or not Path(dct).exists():
            messagebox.showerror("Ошибка", f"Словарь не найден:\n{dct}")
            return

        cmd = [
            hashcat,
            "-m",
            mode,
            "-a",
            "0",
            "-w",
            workload,
            "--status",
            "--status-timer",
            "10",
            hash_file,
            dct,
        ]

        self._log_hashcat("")
        self._log_hashcat("Запускаю Hashcat:", "info")
        self._log_hashcat(" ".join(cmd), "info")
        self.hashcat_status_var.set("Hashcat работает...")
        self.btn_run_hashcat.config(state="disabled")
        self.btn_stop_hashcat.config(state="normal")

        threading.Thread(target=self._hashcat_worker, args=(cmd,), daemon=True).start()

    def _hashcat_worker(self, cmd):
        try:
            self.hashcat_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if self.hashcat_proc.stdout:
                for line in self.hashcat_proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue

                    low = line.lower()
                    tag = None
                    if "status" in low or "speed" in low or "progress" in low:
                        tag = "info"
                    if "cracked" in low or "recovered" in low:
                        tag = "ok"
                    if "error" in low or "exception" in low or "failed" in low:
                        tag = "err"

                    self.after(0, self._log_hashcat, line, tag)

            self.hashcat_proc.wait()
            rc = self.hashcat_proc.returncode

            if rc == 0:
                self.after(0, self._log_hashcat, "✓ Hashcat завершился успешно. Проверь вывод выше и potfile.", "ok")
                self.after(0, lambda: self.hashcat_status_var.set("Hashcat завершён"))
            else:
                self.after(0, self._log_hashcat, f"Hashcat завершился с кодом {rc}", "err")
                self.after(0, lambda: self.hashcat_status_var.set(f"Hashcat завершён с кодом {rc}"))
        except Exception as exc:
            self.after(0, self._log_hashcat, f"Ошибка запуска Hashcat: {exc}", "err")
            self.after(0, lambda: self.hashcat_status_var.set("Ошибка запуска Hashcat"))
        finally:
            self.hashcat_proc = None
            self.after(0, lambda: self.btn_run_hashcat.config(state="normal"))
            self.after(0, lambda: self.btn_stop_hashcat.config(state="disabled"))

    def _stop_hashcat(self):
        if self.hashcat_proc:
            try:
                self.hashcat_proc.terminate()
            except Exception:
                try:
                    self.hashcat_proc.kill()
                except Exception:
                    pass

            self._log_hashcat("⏹ Hashcat остановлен пользователем.", "err")
            self.hashcat_status_var.set("Hashcat остановлен")

    # ── Баланс адресов ────────────────────────────────────────────────────────
    def _looks_like_btc_address(self, value):
        if not value:
            return False
        value = value.strip()

        if value.lower().startswith("bc1") and 14 <= len(value) <= 90:
            return True
        if value[0] in ("1", "3") and 26 <= len(value) <= 35:
            return True
        return False

    def _get_addresses_from_text(self):
        raw = self.address_text.get("1.0", "end")
        addresses = []

        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.replace(",", " ").replace(";", " ").split()
            for part in parts:
                if self._looks_like_btc_address(part):
                    addresses.append(part)
                    break

        return unique_keep_order(addresses)

    def _load_addresses_file(self):
        path = filedialog.askopenfilename(
            title="Загрузить адреса",
            filetypes=[("Text", "*.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = f.read()
        except UnicodeDecodeError:
            with open(path, encoding="cp1251", errors="ignore") as f:
                data = f.read()

        self.address_text.delete("1.0", "end")
        self.address_text.insert("1.0", data)

    def _extract_addresses_from_file(self):
        path = filedialog.askopenfilename(
            title="Извлечь BTC-адреса из файла",
            filetypes=[("Text/JSON/CSV", "*.txt *.json *.csv *.log"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        try:
            try:
                data = Path(path).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                data = Path(path).read_text(encoding="cp1251", errors="ignore")

            candidates = re.findall(r"\b(?:bc1[ac-hj-np-z02-9]{11,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b", data, flags=re.IGNORECASE)
            addresses = unique_keep_order([a.strip() for a in candidates if self._looks_like_btc_address(a.strip())])
            if not addresses:
                messagebox.showwarning("Адреса не найдены", "В выбранном файле не удалось найти BTC-адреса.")
                return

            old_addresses = self._get_addresses_from_text()
            merged = unique_keep_order(old_addresses + addresses)
            self.address_text.delete("1.0", "end")
            self.address_text.insert("1.0", "\n".join(merged) + "\n")
            self._log_balance(f"Из файла извлечено {len(addresses)} адресов, всего в списке: {len(merged)}", "ok")
            self.balance_summary_var.set(f"Готово к проверке: {len(merged)} адресов")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось извлечь адреса:\n{exc}")

    def _clear_addresses(self):
        self.address_text.delete("1.0", "end")
        self.balance_summary_var.set("Итого: —")
        self.balance_log.configure(state="normal")
        self.balance_log.delete("1.0", "end")
        self.balance_log.configure(state="disabled")

    def _check_balances(self):
        addresses = self._get_addresses_from_text()
        if not addresses:
            messagebox.showerror("Ошибка", "Нет валидных BTC-адресов. Вставь адреса по одному на строку.")
            return

        api_base = self.balance_api_base.get().strip().rstrip("/")
        if not api_base:
            messagebox.showerror("Ошибка", "Укажи API endpoint.")
            return

        self.balance_log.configure(state="normal")
        self.balance_log.delete("1.0", "end")
        self.balance_log.configure(state="disabled")
        self.balance_summary_var.set(f"Проверяю {len(addresses)} адресов...")
        self.btn_check_balance.config(state="disabled")

        threading.Thread(target=self._check_balances_worker, args=(api_base, addresses), daemon=True).start()

    def _fetch_address_info(self, api_base, address):
        url = api_base + "/address/" + address
        request = urllib.request.Request(url, headers={"User-Agent": "wallet-recovery-gui/1.0"})

        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read().decode("utf-8")

        return json.loads(data)

    def _check_balances_worker(self, api_base, addresses):
        total_confirmed = 0
        total_mempool = 0
        ok_count = 0

        try:
            self.after(0, self._log_balance, f"API: {api_base}", "info")
            self.after(0, self._log_balance, f"Адресов: {len(addresses)}", "info")
            self.after(0, self._log_balance, "─" * 70)

            for idx, address in enumerate(addresses, start=1):
                try:
                    info = self._fetch_address_info(api_base, address)
                    chain = info.get("chain_stats", {})
                    mempool = info.get("mempool_stats", {})

                    confirmed = int(chain.get("funded_txo_sum", 0)) - int(chain.get("spent_txo_sum", 0))
                    unconfirmed = int(mempool.get("funded_txo_sum", 0)) - int(mempool.get("spent_txo_sum", 0))
                    tx_count = int(chain.get("tx_count", 0)) + int(mempool.get("tx_count", 0))

                    total_confirmed += confirmed
                    total_mempool += unconfirmed
                    ok_count += 1

                    confirmed_btc = confirmed / 100_000_000
                    unconfirmed_btc = unconfirmed / 100_000_000
                    tag = "ok" if confirmed or unconfirmed else None

                    self.after(
                        0,
                        self._log_balance,
                        f"{idx}/{len(addresses)} {address} | confirmed: {confirmed_btc:.8f} BTC | mempool: {unconfirmed_btc:.8f} BTC | tx: {tx_count}",
                        tag,
                    )
                except Exception as exc:
                    self.after(0, self._log_balance, f"{idx}/{len(addresses)} {address} | ошибка: {exc}", "err")

            total_btc = total_confirmed / 100_000_000
            mempool_btc = total_mempool / 100_000_000
            summary = f"Итого: confirmed {total_btc:.8f} BTC | mempool {mempool_btc:.8f} BTC | проверено {ok_count}/{len(addresses)}"

            self.after(0, lambda: self.balance_summary_var.set(summary))
            self.after(0, self._log_balance, "─" * 70)
            self.after(0, self._log_balance, summary, "ok" if total_confirmed or total_mempool else "info")
        finally:
            self.after(0, lambda: self.btn_check_balance.config(state="normal"))


if __name__ == "__main__":
    app = App()
    app.mainloop()
