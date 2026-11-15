import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
import json
import sqlite3
import re
import math

# Google Generative AI (Gemini)
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# gspread & Google Auth
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# ページ基本設定
# ==========================================
st.set_page_config(
    page_title="AI学習パートナー - 松江北高理数科・医学部特化",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="auto"
)

# スマホ画面最適化 CSS
st.markdown("""
<style>
    /* スマホ画面の余白調整 */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
        }
        /* タブのフォントとタップ領域 */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            overflow-x: auto;
            white-space: nowrap;
            -webkit-overflow-scrolling: touch;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 0.88rem !important;
            padding: 8px 10px !important;
        }
        /* ボタンのタップしやすさ向上 */
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 0.95rem;
        }
        /* メトリクスの数字サイズ */
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 定数・設定
# ==========================================
DB_PATH = os.path.join(os.path.dirname(__file__), "ai_study_partner.db")
DEFAULT_SPREADSHEET_ID = "1ZFTjAOHDhlk8S3e35gEwxy-LXfupl7x_86s4lqKWFEw"
DEFAULT_NOTEBOOKLM_URL = "https://notebooklm.google.com/"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def extract_spreadsheet_id(input_str: str) -> str:
    input_str = input_str.strip()
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", input_str)
    if match:
        return match.group(1)
    return input_str

# ==========================================
# ローカルSQLiteデータベース（自動保存エンジン）
# ==========================================

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_local_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS study_logs (
            log_id TEXT PRIMARY KEY,
            date TEXT,
            subject TEXT,
            task_name TEXT,
            target_hours REAL,
            actual_hours REAL,
            completed INTEGER,
            exp_earned INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS weakness_db (
            id TEXT PRIMARY KEY,
            subject TEXT,
            unit TEXT,
            topic TEXT,
            miss_reason TEXT,
            hint TEXT,
            interval_days INTEGER,
            last_reviewed TEXT,
            retention_rate INTEGER,
            status TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS target_roadmap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            title TEXT,
            target_date TEXT,
            progress_or_score TEXT,
            memo TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_name TEXT,
            date TEXT,
            math_dev REAL,
            eng_dev REAL,
            sci_dev REAL,
            total_dev REAL,
            school_rank TEXT,
            memo TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unit_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            unit_name TEXT,
            status TEXT,
            focus_gold_ok INTEGER,
            updated_at TEXT
        )
    """)
    conn.commit()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # target_roadmap シード
    cur.execute("SELECT COUNT(*) FROM target_roadmap")
    if cur.fetchone()[0] == 0:
        seed_roadmap = [
            ("exam", "国公立大医学部 前期日程", "2029-02-25", "現役合格目標", "本番最重要ターゲット"),
            ("exam", "大学入学共通テスト", "2029-01-14", "得点率 90%目標", "新課程・高得点必須"),
            ("exam", "駿台 高1全国模試", "2026-11-29", "偏差値 70以上", "全国レベルでの位置把握"),
            ("exam", "高1 2学期期末テスト", "2026-12-08", "学年トップ5", "松江北高 理数科評定確保"),
            ("subject", "数学 (数I・A 先取り数II・B)", "2027-03-31", "85", "Focus Gold II・B早期完成"),
            ("subject", "英語 (精読・医系基礎単語)", "2027-03-31", "80", "鉄壁・解釈70の定着"),
            ("subject", "物理 (物理基礎・力学基礎)", "2027-03-31", "75", "物理のエッセンス力学編"),
            ("subject", "化学 (化学基礎・物質量・結晶)", "2027-03-31", "88", "モル計算・溶液の性質徹底"),
            ("subject", "国語・情報 (古典文法・情報I)", "2027-03-31", "70", "定期テスト満点目標"),
        ]
        cur.executemany("INSERT INTO target_roadmap (category, title, target_date, progress_or_score, memo) VALUES (?, ?, ?, ?, ?)", seed_roadmap)

    # weakness_db シード
    cur.execute("SELECT COUNT(*) FROM weakness_db")
    if cur.fetchone()[0] == 0:
        seed_weakness = [
            (
                "W-101", "数学I・A", "2次関数・不等式",
                "文字定数を含む2次関数の最大・最小（場合分け）",
                "軸の位置 x = a が区間外・区間内・中央値のいずれにあるかの境界等号忘れ",
                "グラフの軸と定義域の中心 x = (p+q)/2 の位置関係を必ず図示して分類する",
                3, (datetime.date.today() - datetime.timedelta(days=3)).strftime("%Y-%m-%d"), 58, "復習待ち"
            ),
            (
                "W-102", "化学基礎", "物質量・化学反応の量的関係",
                "過不足のある化学反応式のモル計算と気体体積",
                "反応前・変化量・反応後の3段表のモル比換算ミス",
                "化学反応式の係数比＝反応するモル比。グラムやリットルのまま計算しないこと",
                7, (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d"), 42, "復習待ち"
            ),
            (
                "W-103", "物理基礎", "力学（運動の法則）",
                "摩擦力（静止摩擦力と動摩擦力）と斜面上のつりあい",
                "静止摩擦力 f は常に μN ではなく、最大静止摩擦力 μN 以下の外力とつりあう点を見落とした",
                "物体が動き出す瞬間までは「つりあいの式」、滑り出したら動摩擦力 μ'N",
                14, (datetime.date.today() - datetime.timedelta(days=14)).strftime("%Y-%m-%d"), 35, "復習待ち"
            )
        ]
        cur.executemany("INSERT INTO weakness_db VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", seed_weakness)

    # study_logs シード
    cur.execute("SELECT COUNT(*) FROM study_logs")
    if cur.fetchone()[0] == 0:
        seed_logs = []
        for i in range(6, 0, -1):
            past_date = (datetime.date.today() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            seed_logs.append((f"L-00{i}A", past_date, "数学I・A", "Focus Gold 2次関数 難問特訓", 2.5, 2.5, 1, 180))
            seed_logs.append((f"L-00{i}B", past_date, "化学基礎", "モル濃度・溶液調製演習", 1.5, 1.5, 1, 120))
            seed_logs.append((f"L-00{i}C", past_date, "英語", "英文解釈精読＆単語暗記", 1.0, 1.2, 1, 90))
        
        seed_logs.extend([
            ("L-TODAY-1", today_str, "数学I・A", "【数学】2次関数 最大最小 応用演習 3問", 2.5, 2.5, 1, 150),
            ("L-TODAY-2", today_str, "英語", "【英語】英文解釈クラシック＆鉄壁セクション演習", 1.5, 0.0, 0, 100),
            ("L-TODAY-3", today_str, "化学基礎", "【化学】物質量・気体の法則 総合演習", 1.5, 0.0, 0, 120),
            ("L-TODAY-4", today_str, "弱点特訓", "【復習】忘却曲線復習ドリル 2問", 0.5, 0.0, 0, 80),
        ])
        cur.executemany("INSERT INTO study_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?)", seed_logs)

    # chat_history 初期対話シード
    cur.execute("SELECT COUNT(*) FROM chat_history")
    if cur.fetchone()[0] == 0:
        seed_chats = [
            ("assistant", "こんにちは！ソクラテスAIメンターです。松江北高校理数科での勉強や、医学部受験に向けたFocus Gold先取り学習の疑問など、何でも相談してください。まずは「自分がどこまで解けて、どこで手が止まったか」を教えてくださいね。", today_str),
            ("user", "数学Iの2次関数で、$y = x^2 - 2ax + 1$ ($0 \\le x \\le 2$) の最大値を求めるとき、なぜ $a < 1$ と $a > 1$ で場合分けするのか、感覚的にしっくりきません…", today_str),
            ("assistant", "良い疑問ですね！丸暗記ではなく感覚で納得したいという姿勢は、医学部数学で極めて重要です。\n\nでは質問です。下に凸の放物線において、頂点から「遠い」点ほど $y$ の値はどうなりますか？\nそして、定義域 $0 \\le x \\le 2$ のちょうど『真ん中（中心）』の値はいくつでしょうか？\n\nこの2つを組み合わせると、なぜ『1』が境界になるのか見えてきませんか？", today_str)
        ]
        cur.executemany("INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)", seed_chats)

    # exam_records シード
    cur.execute("SELECT COUNT(*) FROM exam_records")
    if cur.fetchone()[0] == 0:
        seed_exams = [
            ("高1 1学期期末テスト", "2026-07-08", 68.5, 62.0, 66.0, 65.5, "学年 12位 / 280人", "数学の計算精度が好調"),
            ("第1回 駿台高1全国模試", "2026-08-25", 66.0, 63.5, 64.0, 64.5, "理数科 8位", "記述の論理展開に課題"),
            ("高1 2学期中間テスト", "2026-10-15", 71.0, 65.0, 68.5, 68.2, "学年 6位 / 280人", "2次関数の先取りが奏功・医学部B判定到達"),
        ]
        cur.executemany("INSERT INTO exam_records (exam_name, date, math_dev, eng_dev, sci_dev, total_dev, school_rank, memo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", seed_exams)

    # unit_progress (Focus Gold・理科 単元別マスター) シード
    cur.execute("SELECT COUNT(*) FROM unit_progress")
    if cur.fetchone()[0] == 0:
        seed_units = [
            # 数学I・A
            ("数学I・A", "数と式・実数・集合と命題", "一通り完了 🔵", 1, today_str),
            ("数学I・A", "2次関数（最大最小・場合分け）", "学習中 🟡", 0, today_str),
            ("数学I・A", "2次方程式・2次不等式", "一通り完了 🔵", 1, today_str),
            ("数学I・A", "図形と計量（三角比・正弦余弦定理）", "学習中 🟡", 0, today_str),
            ("数学I・A", "場合の数と順列・組合せ", "一通り完了 🔵", 1, today_str),
            ("数学I・A", "確率（条件付き確率・期待値）", "学習中 🟡", 0, today_str),
            ("数学I・A", "図形の性質（チェバ・メネラウス・円）", "学習中 🟡", 0, today_str),
            ("数学I・A", "データの分析・仮説検定", "未着手 ⚪", 0, today_str),
            # 数学II・B（先取り）
            ("数学II・B 先取り", "式と証明・複素数と方程式", "学習中 🟡", 0, today_str),
            ("数学II・B 先取り", "図形と方程式（軌跡と領域）", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "三角関数（加法定理・合成）", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "指数関数・対数関数", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "微分法（接線・極大極小・最大最小）", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "積分法（定積分・面積計算）", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "数列（等差等比・漸化式・数学的帰納法）", "未着手 ⚪", 0, today_str),
            ("数学II・B 先取り", "ベクトル（平面・空間ベクトル）", "未着手 ⚪", 0, today_str),
            # 物理基礎
            ("物理基礎", "速度・等加速度直線運動", "Focus Goldマスター 🎓", 1, today_str),
            ("物理基礎", "落体の運動（自由落下・投射）", "一通り完了 🔵", 1, today_str),
            ("物理基礎", "力のつりあい・作用反作用", "一通り完了 🔵", 1, today_str),
            ("物理基礎", "運動の法則（運動方程式 ma=F）", "学習中 🟡", 0, today_str),
            ("物理基礎", "摩擦力・斜面上の物体の運動", "学習中 🟡", 0, today_str),
            ("物理基礎", "圧力・浮力・気体の圧力", "学習中 🟡", 0, today_str),
            ("物理基礎", "仕事と力学的エネルギー保存則", "未着手 ⚪", 0, today_str),
            # 化学基礎
            ("化学基礎", "物質の分類・原子の構造・周期表", "Focus Goldマスター 🎓", 1, today_str),
            ("化学基礎", "化学結合（イオン・共有・金属）と結晶", "一通り完了 🔵", 1, today_str),
            ("化学基礎", "物質量（mol）とアボガドロ定数", "学習中 🟡", 0, today_str),
            ("化学基礎", "溶液の濃度（質量パーセント・モル濃度）", "学習中 🟡", 0, today_str),
            ("化学基礎", "化学反応式と量的関係計算", "学習中 🟡", 0, today_str),
            ("化学基礎", "酸・塩基の定義とpH・中和滴定", "未着手 ⚪", 0, today_str),
            ("化学基礎", "酸化還元反応と酸化数", "未着手 ⚪", 0, today_str),
        ]
        cur.executemany("INSERT INTO unit_progress (subject, unit_name, status, focus_gold_ok, updated_at) VALUES (?, ?, ?, ?, ?)", seed_units)

    conn.commit()
    conn.close()

init_local_db()

def local_get_study_logs() -> pd.DataFrame:
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM study_logs ORDER BY date ASC, log_id ASC", conn)
    conn.close()
    df["completed"] = df["completed"].astype(bool)
    return df

def local_update_task_completed(log_id: str, completed: bool):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE study_logs SET completed = ? WHERE log_id = ?", (1 if completed else 0, log_id))
    conn.commit()
    conn.close()

def local_set_today_plan_tasks(tasks: list[dict]):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM study_logs WHERE date = ? AND completed = 0", (today_str,))
    for i, t in enumerate(tasks):
        log_id = f"L-PLAN-{i+1}"
        cur.execute("INSERT OR REPLACE INTO study_logs VALUES (?, ?, ?, ?, ?, 0.0, 0, ?)",
                    (log_id, today_str, t["subject"], t["task_name"], t["hours"], t["exp"]))
    conn.commit()
    conn.close()

def local_get_meta(key: str, default: str = "") -> str:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default

def local_set_meta(key: str, value: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def local_get_streak_days() -> int:
    val = local_get_meta("streak_days", "28")
    try:
        return int(val)
    except ValueError:
        return 28

def local_checkout_today(note: str, feedback: str) -> int:
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    last_date = local_get_meta("last_checkout_date", "")
    current_streak = local_get_streak_days()
    
    if last_date != today_str:
        current_streak += 1
        local_set_meta("streak_days", str(current_streak))
        local_set_meta("last_checkout_date", today_str)
        
    local_set_meta("today_checkout_note", note)
    local_set_meta("today_checkout_feedback", feedback)
    return current_streak

def local_get_weakness_db() -> pd.DataFrame:
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM weakness_db", conn)
    conn.close()
    return df

def local_evaluate_weakness_review(weakness_id: str, rating: str) -> tuple[int, int, str]:
    """
    エビングハウス忘却曲線に基づき復習間隔・保持率・EXPを自動再計算してDB更新
    戻り値: (next_interval, next_retention, message)
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM weakness_db WHERE id = ?", (weakness_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return 1, 50, "問題が見つかりません"

    current_interval = row["interval_days"] or 1
    current_retention = row["retention_rate"] or 50
    topic_name = row["topic"] or "復習問題"
    
    stages = [1, 3, 7, 14, 30]
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    if rating == "perfect": # 🟢 完璧に解けた
        # 次のステージへ延伸
        if current_interval in stages:
            idx = stages.index(current_interval)
            next_interval = stages[min(idx + 1, len(stages) - 1)]
        else:
            next_interval = current_interval * 2
            
        next_retention = min(current_retention + 25, 95)
        status = "完全定着マスター 🎓" if current_interval >= 30 else "復習待ち"
        exp_gain = 120
        msg = f"🎉 完璧！自力でクリア！次回の復習は【{next_interval}日後】です（+{exp_gain} EXP）"

    elif rating == "good": # 🟡 ギリギリ / ヒント見た
        next_interval = current_interval # 間隔維持
        next_retention = max(current_retention, 65)
        status = "復習待ち"
        exp_gain = 60
        msg = f"👍 定着確認！間隔【{next_interval}日】を維持してもう一度定着させます（+{exp_gain} EXP）"

    else: # 🔴 解けなかった
        next_interval = 1 # 1日後に即座にリセット
        next_retention = 35
        status = "要復習 🚨"
        exp_gain = 30
        msg = f"💪 復習した努力を評価！忘れないよう【明日（1日後）】に再出題します（+{exp_gain} EXP）"

    # weakness_db の更新
    cur.execute(
        "UPDATE weakness_db SET interval_days = ?, retention_rate = ?, status = ?, last_reviewed = ? WHERE id = ?",
        (next_interval, next_retention, status, today_str, weakness_id)
    )
    
    # 獲得EXPを study_logs に追加記録
    exp_log_id = f"L-EXP-{weakness_id}-{datetime.datetime.now().strftime('%H%M%S')}"
    cur.execute(
        "INSERT OR REPLACE INTO study_logs VALUES (?, ?, '復習特訓', ?, 0.25, 0.25, 1, ?)",
        (exp_log_id, today_str, f"【忘却復習】{topic_name}", exp_gain)
    )
    
    conn.commit()
    conn.close()
    return next_interval, next_retention, msg

def local_mark_weakness_reviewed(weakness_id: str):
    """旧関数互換"""
    local_evaluate_weakness_review(weakness_id, "perfect")

def local_add_weakness_record(data: dict) -> str:
    """スマホ写真OCRから直接weakness_dbに新規登録"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM weakness_db")
    cnt = cur.fetchone()[0]
    new_id = f"W-{cnt+101}"
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cur.execute(
        "INSERT INTO weakness_db VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            new_id,
            data.get("subject", "数学I・A"),
            data.get("unit", "未分類単元"),
            data.get("topic", "スマホ撮影問題"),
            data.get("miss_reason", "誤答分析"),
            data.get("hint", "定義に立ち返って考えよう"),
            data.get("interval_days", 1),
            today_str,
            data.get("retention_rate", 50),
            "復習待ち"
        )
    )
    conn.commit()
    conn.close()
    return new_id

def local_get_target_roadmap() -> pd.DataFrame:
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM target_roadmap", conn)
    conn.close()
    return df

def local_get_chat_history() -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM chat_history ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]

def local_add_chat_message(role: str, content: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)",
                (role, content, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def local_get_exam_records() -> pd.DataFrame:
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM exam_records ORDER BY date ASC", conn)
    conn.close()
    return df

def local_add_exam_record(exam_name: str, date_str: str, math_dev: float, eng_dev: float, sci_dev: float, total_dev: float, school_rank: str, memo: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO exam_records (exam_name, date, math_dev, eng_dev, sci_dev, total_dev, school_rank, memo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (exam_name, date_str, math_dev, eng_dev, sci_dev, total_dev, school_rank, memo)
    )
    conn.commit()
    conn.close()

def local_get_unit_progress(subject: str = None) -> pd.DataFrame:
    conn = get_db_connection()
    if subject:
        df = pd.read_sql_query("SELECT * FROM unit_progress WHERE subject = ? ORDER BY id ASC", conn, params=(subject,))
    else:
        df = pd.read_sql_query("SELECT * FROM unit_progress ORDER BY id ASC", conn)
    conn.close()
    if not df.empty and "focus_gold_ok" in df.columns:
        df["focus_gold_ok"] = df["focus_gold_ok"].astype(bool)
    return df

def local_update_unit_progress(unit_id: int, status: str, focus_gold_ok: bool):
    conn = get_db_connection()
    cur = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cur.execute(
        "UPDATE unit_progress SET status = ?, focus_gold_ok = ?, updated_at = ? WHERE id = ?",
        (status, 1 if focus_gold_ok else 0, today_str, unit_id)
    )
    conn.commit()
    conn.close()

def local_add_unit_progress(subject: str, unit_name: str, status: str = "未着手 ⚪", focus_gold_ok: bool = False):
    conn = get_db_connection()
    cur = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cur.execute(
        "INSERT INTO unit_progress (subject, unit_name, status, focus_gold_ok, updated_at) VALUES (?, ?, ?, ?, ?)",
        (subject, unit_name, status, 1 if focus_gold_ok else 0, today_str)
    )
    conn.commit()
    conn.close()

# ==========================================
# Gemini API モジュール
# ==========================================

def get_gemini_api_key() -> str:
    if "gemini_api_key" in st.session_state and st.session_state["gemini_api_key"]:
        return st.session_state["gemini_api_key"]
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ.get("GEMINI_API_KEY")
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
    return ""

def call_gemini(prompt: str, system_instruction: str = None) -> str:
    api_key = get_gemini_api_key()
    if not api_key or not HAS_GENAI:
        return None
    try:
        genai.configure(api_key=api_key)
        target_model = st.session_state.get("selected_gemini_model", "gemini-3.6-flash")
        model_candidates = [target_model, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro", "gemini-2.0-flash", "gemini-1.5-flash"]
        for m_name in model_candidates:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=system_instruction
                )
                resp = model.generate_content(prompt)
                return resp.text
            except Exception:
                continue
        return None
    except Exception as e:
        st.error(f"Gemini API 呼び出しエラー: {e}")
        return None

def analyze_image_with_gemini_py(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple[dict, bool]:
    """
    スマホで撮影した問題写真から Gemini 3.6 Flash が直接OCR・誤答解析
    戻り値: (解析結果dict, 実際のAPI呼び出しに成功したかbool)
    """
    api_key = get_gemini_api_key()
    if not api_key or not HAS_GENAI:
        return None, False
    try:
        genai.configure(api_key=api_key)
        target_model = st.session_state.get("selected_gemini_model", "gemini-3.6-flash")
        model = genai.GenerativeModel(model_name=target_model)
        
        prompt = """
        あなたは松江北高校 理数科（高校1年生）の医学部受験指導責任者です。
        添付された画像は、生徒がスマホで撮影した「問題用紙・Focus Gold・ノート・答案」です。
        画像を精密に読み取り、以下の判定・解析を行ってください。

        【重要判定ルール】
        もし画像が勉強のプリント・問題集・ノート・答案ではなく、人物の顔写真や風景、無関係な物体である場合は、
        必ず {"is_study_material": false, "message": "画像内に勉強の問題や手書き答案が見当たりません。問題集やプリントの写真を撮影してください。"} とだけ出力してください。

        【勉強の問題・答案の場合の出力JSONフォーマット】
        {
          "is_study_material": true,
          "subject": "科目名（数学I・A、化学基礎、物理基礎、英語 など）",
          "unit": "単元名（例: 2次関数と不等式、物質量と化学反応式、運動の法則 など）",
          "topic": "具体的な論点・問題テーマ（例: 文字定数を含む2次関数の最大最小）",
          "miss_reason": "生徒が間違えた具体的な原因・計算ミスや思考の盲点",
          "hint": "ソクラテス的に本質を自力で気付かせるための着眼点ヒント",
          "focus_gold_ref": "Focus Goldまたは教科書の該当例題・類題目安（例: Focus Gold 数I 例題64〜68）",
          "interval_days": 1,
          "retention_rate": 50
        }
        """
        image_part = {
            "mime_type": mime_type,
            "data": image_bytes
        }
        response = model.generate_content([prompt, image_part])
        clean_text = re.sub(r"^```json\s*", "", response.text.strip())
        clean_text = re.sub(r"\s*```$", "", clean_text)
        return json.loads(clean_text), True
    except Exception as e:
        st.error(f"画像OCR解析エラー: {e}")
        return None, False

# ==========================================
# Googleスプレッドシート連携（フォールバック）
# ==========================================

@st.cache_resource
def get_gspread_client():
    try:
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            creds_info = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            return gspread.authorize(creds)
    except Exception:
        pass

    candidate_paths = [
        os.path.join(os.path.dirname(__file__), "credentials.json"),
        os.path.join(os.path.dirname(__file__), "service_account.json"),
        os.path.join(os.path.dirname(__file__), ".streamlit", "credentials.json"),
        os.path.join(os.path.dirname(__file__), ".streamlit", "service_account.json"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                creds = Credentials.from_service_account_file(path, scopes=SCOPES)
                return gspread.authorize(creds)
            except Exception:
                pass
    return None

def get_spreadsheet(sheet_id: str = None):
    client = get_gspread_client()
    if client is None:
        return None
    target_id = sheet_id or st.session_state.get("spreadsheet_id", DEFAULT_SPREADSHEET_ID)
    try:
        return client.open_by_key(target_id)
    except Exception:
        return None

def fetch_sheet_data(sheet_name: str) -> tuple[pd.DataFrame, bool]:
    sh = get_spreadsheet()
    if sh is None:
        if sheet_name == "target_roadmap":
            return local_get_target_roadmap(), False
        elif sheet_name == "weakness_db":
            return local_get_weakness_db(), False
        elif sheet_name == "study_logs":
            return local_get_study_logs(), False
        return pd.DataFrame(), False

    try:
        worksheet = sh.worksheet(sheet_name)
        records = worksheet.get_all_records()
        if records:
            return pd.DataFrame(records), True
        else:
            return local_get_study_logs(), True
    except Exception:
        if sheet_name == "target_roadmap":
            return local_get_target_roadmap(), False
        elif sheet_name == "weakness_db":
            return local_get_weakness_db(), False
        elif sheet_name == "study_logs":
            return local_get_study_logs(), False
        return pd.DataFrame(), False

# ==========================================
# サイドバー: 設定 & プロファイル & NotebookLM
# ==========================================
with st.sidebar:
    st.title("🎓 AI Study Partner")
    st.caption("松江北高 理数科・医学部現役合格プログラム")
    
    st.divider()
    
    # 1. Gemini API 設定
    st.subheader("🤖 AI頭脳 (Gemini API)")
    gemini_key_input = st.text_input(
        "Gemini API Key:",
        value=get_gemini_api_key(),
        type="password",
        help="Google AI Studioで取得したAPIキーを入力してください"
    )
    if gemini_key_input:
        st.session_state["gemini_api_key"] = gemini_key_input
        st.success("🟢 Gemini API 稼働中", icon="✨")
    else:
        st.info("ℹ️ キー未設定（シミュレーションAIが稼働中）")

    # 公式プラン（Google AI Plus）対応モデル選択
    model_options = {
        "gemini-3.6-flash": "3.6 Flash（あらゆる場面でサポート ⚡ ※おすすめ）",
        "gemini-3.5-flash-lite": "3.5 Flash-Lite（すばやく回答を得るのに最適 🚀）",
        "gemini-3.1-pro": "3.1 Pro（高度な推論 🧠）",
        "gemini-4-argon": "4 Argon（複雑なタスク 🔒 Google AI Pro限定）"
    }
    selected_model_key = st.selectbox(
        "🧠 稼働モデル選択:",
        options=list(model_options.keys()),
        format_func=lambda k: model_options[k],
        index=0,
        help="お使いのGoogle AI Plusプラン（3.6 Flash）に合わせて最適化されています"
    )
    st.session_state["selected_gemini_model"] = selected_model_key

    st.divider()

    # 2. 知識検索基盤: NotebookLM 連携
    st.subheader("📚 知識ベース: NotebookLM")
    st.caption("Focus Gold や 松江北高プリントPDFを格納したナレッジ検索")
    notebooklm_url = st.text_input(
        "NotebookLM URL:",
        value=st.session_state.get("notebooklm_url", DEFAULT_NOTEBOOKLM_URL),
        help="あなたのNotebookLMノートブックのURLを貼り付けてください"
    )
    st.session_state["notebooklm_url"] = notebooklm_url
    st.link_button("🚀 NotebookLMを開く", notebooklm_url, use_container_width=True)

    st.divider()

    # 3. データ保存状態
    st.subheader("💾 データ保存ステータス")
    st.success("🟢 ローカル自動保存: 有効 (SQLite)", icon="💾")
    st.caption("※タスク完了やチャット履歴はPC内に自動保存されています。")

    # スプレッドシート連携（任意）
    with st.expander("📊 Googleスプレッドシート連携（任意）"):
        input_sheet = st.text_input(
            "スプレッドシートID または URL",
            value=st.session_state.get("spreadsheet_input", DEFAULT_SPREADSHEET_ID),
        )
        current_sheet_id = extract_spreadsheet_id(input_sheet)
        st.session_state["spreadsheet_id"] = current_sheet_id
        st.session_state["spreadsheet_input"] = input_sheet
        current_sheet_url = f"https://docs.google.com/spreadsheets/d/{current_sheet_id}/edit"
        
        c_l1, c_l2 = st.columns(2)
        with c_l1:
            st.link_button("📂 シート", current_sheet_url, use_container_width=True)
        with c_l2:
            st.link_button("➕ 新規作成", "https://sheets.new", use_container_width=True)

    st.divider()
    st.subheader("👤 受講生プロフィール")
    st.write("**志望校**: 医学部医学科")
    st.write("**所属**: 松江北高校 理数科（高校1年生）")
    st.write(f"**本日の日付**: {datetime.date.today().strftime('%Y年%m月%d日')}")

# ==========================================
# データの読み込み & ステータス
# ==========================================
df_roadmap, is_roadmap_live = fetch_sheet_data("target_roadmap")
df_weakness, is_weakness_live = fetch_sheet_data("weakness_db")
df_logs, is_logs_live = fetch_sheet_data("study_logs")

today_str = datetime.date.today().strftime("%Y-%m-%d")
today_logs = df_logs[df_logs["date"] == today_str] if not df_logs.empty and "date" in df_logs.columns else pd.DataFrame()
total_today_exp = int(today_logs[today_logs["completed"] == True]["exp_earned"].sum()) if not today_logs.empty and "exp_earned" in today_logs.columns else 0
total_today_hours = float(today_logs[today_logs["completed"] == True]["target_hours"].sum()) if not today_logs.empty and "target_hours" in today_logs.columns else 0.0

with st.sidebar:
    st.divider()
    st.subheader("⚡ 本日のクイックステータス")
    streak_count = local_get_streak_days()
    is_checked_out = local_get_meta("last_checkout_date") == today_str
    st.metric(label="連続学習記録", value=f"{streak_count}日連続 🔥", delta="本日達成済 ✅" if is_checked_out else "本日分未完了")
    st.metric(label="本日獲得EXP", value=f"{total_today_exp} EXP", delta="目標 500 EXP")
    st.metric(label="本日の学習時間", value=f"{total_today_hours:.1f} 時間")

# ==========================================
# メイン画面ヘッダー
# ==========================================
st.title("AI学習パートナー 🚀")
st.caption("松江北高校 理数科・医学部現役合格プログラム｜スマホ撮影OCR × Gemini 3.6 Flash × NotebookLM")

# タブ構成（5つのタブ）
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 今日の作戦会議",
    "🏠 本日のダッシュボード",
    "🔄 弱点克服＆復習ドリル",
    "📈 全体ロードマップ",
    "💬 24時間質問部屋"
])

# ==========================================
# タブ1: 🎯 今日の作戦会議（帰宅後〜夜の集中プランニング）
# ==========================================
with tab1:
    st.header("🎯 放課後・夜の作戦会議（Today's Strategy）")
    st.caption("学校から帰ってきたら、まずここを開いて今日の学習を組み立てましょう。残された時間や今日の疲労度に合わせて、**AIが科目配分・予想EXPを動的リアルタイム再計算**します。")
    
    col_input1, col_input2, col_input3 = st.columns([1, 1, 1])
    with col_input1:
        target_hours = st.slider("🎯 帰宅後の目標学習時間 (時間)", min_value=1.0, max_value=14.0, value=3.5, step=0.5, help="平日帰宅後は3〜4時間、休日は6〜10時間などその日の状況に合わせて選べます")
    with col_input2:
        study_style = st.selectbox(
            "⚡ 本日の希望スタイル",
            [
                "バランス進行型（数I・A・理科・英語を均等に前進）",
                "数学・理科 突破型（宿題＋Focus Gold難問特訓）",
                "弱点集中メンテナンス型（忘却曲線ドリル＋解き直し）",
                "定期テスト・模試対策型（松江北高 理数科カリキュラム対応）",
                "先取り特訓型（数II・B Focus Gold先行攻略）"
            ]
        )
    with col_input3:
        condition = st.select_slider(
            "🧠 本日の集中度・疲労度コンディション",
            options=["学校帰り・疲労気味 🥱", "ひと息ついてリセット ☕", "集中モード突入 ⚡", "休日・ゾーン突入 🔥"],
            value="ひと息ついてリセット ☕"
        )
    
    condition_multipliers = {
        "学校帰り・疲労気味 🥱": 0.85,
        "ひと息ついてリセット ☕": 1.0,
        "集中モード突入 ⚡": 1.15,
        "休日・ゾーン突入 🔥": 1.3
    }
    c_mul = condition_multipliers.get(condition, 1.0)
    
    # 動的再計算
    h_a_math = round(target_hours * 0.40, 1)
    h_a_eng  = round(target_hours * 0.25, 1)
    h_a_chem = round(target_hours * 0.25, 1)
    h_a_rev  = round(max(target_hours - (h_a_math + h_a_eng + h_a_chem), 0.5), 1)
    exp_a    = int(target_hours * 80 * c_mul)
    
    h_b_math = round(target_hours * 0.50, 1)
    h_b_phys = round(target_hours * 0.30, 1)
    h_b_chem = round(target_hours * 0.15, 1)
    h_b_out  = round(max(target_hours - (h_b_math + h_b_phys + h_b_chem), 0.5), 1)
    exp_b    = int(target_hours * 90 * c_mul)
    
    h_c_weak = round(target_hours * 0.35, 1)
    h_c_eng  = round(target_hours * 0.25, 1)
    h_c_chem = round(target_hours * 0.25, 1)
    h_c_self = round(max(target_hours - (h_c_weak + h_c_eng + h_c_chem), 0.5), 1)
    exp_c    = int(target_hours * 70 * c_mul)

    st.markdown("---")
    
    c_head, c_btn = st.columns([3, 1])
    with c_head:
        st.subheader(f"🤖 AI動的再計算プラン（本日の目標: {target_hours}時間 × {condition}）")
    with c_btn:
        generate_ai_plan = st.button("✨ Geminiに特注プラン考案", use_container_width=True)

    if generate_ai_plan and get_gemini_api_key():
        with st.spinner("Geminiがオーダーメイドプランを考案中..."):
            prompt = f"受講生: 松江北高理数科高1（医学部志望）。目標{target_hours}時間、スタイル:{study_style}、体調:{condition}。各教科の時間配分と狙いを3行でアドバイスしてください。"
            custom_res = call_gemini(prompt)
            if custom_res:
                st.session_state["custom_ai_plan"] = custom_res

    if "custom_ai_plan" in st.session_state:
        with st.container(border=True):
            st.markdown("#### 🌟 Geminiからの個別アドバイス")
            st.markdown(st.session_state["custom_ai_plan"])

    plan_col1, plan_col2, plan_col3 = st.columns(3)
    
    with plan_col1:
        with st.container(border=True):
            st.markdown("### 🅰️ プランA: 王道バランス")
            st.caption("全科目をバランスよく伸ばす基本設計")
            st.markdown(f"""
            - **数学I・A 演習**: `{h_a_math}h`
            - **英語 精読・語彙**: `{h_a_eng}h`
            - **化学基礎 物質量**: `{h_a_chem}h`
            - **忘却復習ドリル**: `{h_a_rev}h`
            """)
            st.metric(label="動的予想獲得EXP", value=f"+{exp_a} EXP", delta=f"{int(c_mul*100)}% 効率")
            st.badge("推奨度: ★★★★★", icon="✨")
    
    with plan_col2:
        with st.container(border=True):
            st.markdown("### 🅱️ プランB: 数・理 突破")
            st.caption("理数科の武器を極限まで強化")
            st.markdown(f"""
            - **数学 Focus Gold難問**: `{h_b_math}h`
            - **物理基礎 力学特訓**: `{h_b_phys}h`
            - **化学基礎 溶液・結晶**: `{h_b_chem}h`
            - **ファインマン解説**: `{h_b_out}h`
            """)
            st.metric(label="動的予想獲得EXP", value=f"+{exp_b} EXP", delta=f"{int(c_mul*100)}% 効率")
            st.badge("推奨度: ★★★★☆", icon="🔥")
            
    with plan_col3:
        with st.container(border=True):
            st.markdown("### 🅲 プランC: 弱点総ざらい")
            st.caption("忘却曲線の黄色信号を徹底メンテナンス")
            st.markdown(f"""
            - **苦手単元 集中特訓**: `{h_c_weak}h`
            - **英文法・構文復習**: `{h_c_eng}h`
            - **理科基礎 用語暗記**: `{h_c_chem}h`
            - **解き直し自己解説**: `{h_c_self}h`
            """)
            st.metric(label="動的予想獲得EXP", value=f"+{exp_c} EXP", delta=f"{int(c_mul*100)}% 効率")
            st.badge("推奨度: ★★★☆☆", icon="🛡️")

    selected_plan = st.radio("採用するプランを選択してください:", ["プランA（王道バランス）", "プランB（数・理 突破）", "プランC（弱点総ざらい）"], horizontal=True)
    
    if st.button("🚀 このプランで本日のスケジュールを確定する", type="primary", use_container_width=True):
        if "プランA" in selected_plan:
            tasks_to_set = [
                {"subject": "数学I・A", "task_name": f"【数学】2次関数・確率 演習 ({h_a_math}h)", "hours": h_a_math, "exp": int(exp_a*0.4)},
                {"subject": "英語", "task_name": f"【英語】精読＆鉄壁語彙セクション ({h_a_eng}h)", "hours": h_a_eng, "exp": int(exp_a*0.25)},
                {"subject": "化学基礎", "task_name": f"【化学】物質量・溶液 総合演習 ({h_a_chem}h)", "hours": h_a_chem, "exp": int(exp_a*0.25)},
                {"subject": "復習ドリル", "task_name": f"【復習】忘却曲線復習ドリル ({h_a_rev}h)", "hours": h_a_rev, "exp": int(exp_a*0.1)},
            ]
        elif "プランB" in selected_plan:
            tasks_to_set = [
                {"subject": "数学I・A", "task_name": f"【数学】Focus Gold難問・先取り ({h_b_math}h)", "hours": h_b_math, "exp": int(exp_b*0.5)},
                {"subject": "物理基礎", "task_name": f"【物理】力学・運動方程式特訓 ({h_b_phys}h)", "hours": h_b_phys, "exp": int(exp_b*0.3)},
                {"subject": "化学基礎", "task_name": f"【化学】結晶格子・溶液の計算 ({h_b_chem}h)", "hours": h_b_chem, "exp": int(exp_b*0.15)},
                {"subject": "ファインマン", "task_name": f"【解説】ファインマン思考アウトプット ({h_b_out}h)", "hours": h_b_out, "exp": int(exp_b*0.05)},
            ]
        else:
            tasks_to_set = [
                {"subject": "弱点特訓", "task_name": f"【苦手】忘却リスト集中ドリル ({h_c_weak}h)", "hours": h_c_weak, "exp": int(exp_c*0.35)},
                {"subject": "英語", "task_name": f"【英語】英文法・重要構文復習 ({h_c_eng}h)", "hours": h_c_eng, "exp": int(exp_c*0.25)},
                {"subject": "化学基礎", "task_name": f"【化学】用語・基本計算の総ざらい ({h_c_chem}h)", "hours": h_c_chem, "exp": int(exp_c*0.25)},
                {"subject": "解き直し", "task_name": f"【自己解説】誤答原因の自己分析 ({h_c_self}h)", "hours": h_c_self, "exp": int(exp_c*0.15)},
            ]
        local_set_today_plan_tasks(tasks_to_set)
        st.success(f"『{selected_plan}』で本日のタスク（合計 {target_hours}時間 / {sum(t['exp'] for t in tasks_to_set)} EXP）をダッシュボードに反映・保存しました！")
        st.balloons()
        st.rerun()


# ==========================================
# タブ2: 🏠 本日のダッシュボード
# ==========================================
with tab2:
    st.header("🏠 本日のダッシュボード")
    
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(f"""
        **【AIメンターメッセージ】学校お疲れ様でした！**  
        松江北高校での授業や課題を乗り切った自分をまず労いましょう。ひと息ついたら、自分のペースで医学部合格へ一歩前進！  
        今日間違えた問題はスマホで撮影して「弱点克服ドリル」に登録しましょう。タスク完了や復習EXPはすべて自動保存されます ✨
        """)
        
    st.markdown("---")
    
    st.subheader("🎖️ 医学部合格EXPメーター")
    exp_col1, exp_col2, exp_col3 = st.columns([1, 2, 1])
    
    total_accumulated_exp = int(df_logs[df_logs["completed"] == True]["exp_earned"].sum()) if not df_logs.empty and "exp_earned" in df_logs.columns else 3450
    level = 10 + (total_accumulated_exp // 300)
    current_level_exp = total_accumulated_exp % 300
    
    with exp_col1:
        st.metric("現在のレベル", f"Lv. {level}", delta="+1 Lv (今週)")
    with exp_col2:
        st.write(f"**累計EXP**: {total_accumulated_exp:,} EXP（次のレベルまであと {300 - current_level_exp} EXP）")
        st.progress(min(max(current_level_exp / 300, 0.0), 1.0))
    with exp_col3:
        target_today_hours = float(today_logs["target_hours"].sum()) if not today_logs.empty and "target_hours" in today_logs.columns else 6.0
        st.metric("今日の実績時間", f"{total_today_hours:.1f}h / {target_today_hours:.1f}h", delta=f"{int(total_today_hours / target_today_hours * 100) if target_today_hours > 0 else 0}% 達成")
        
    st.markdown("---")
    
    st.subheader("📋 本日やるべきタスク（動的再計算プラン連動）")
    st.caption("チェックを入れると即座にローカルDBへ保存されます。")
    
    if today_logs.empty:
        st.info("本日のタスクはまだありません。「朝の作戦会議」で本日のプランを確定してください。")
    else:
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            completed_flags = []
            for idx, row in today_logs.iterrows():
                log_id = row.get("log_id", f"LOG-{idx}")
                task_label = f"【{row.get('subject', '未設定')}】{row.get('task_name', '')} — +{row.get('exp_earned', 50)} EXP"
                is_done = bool(row.get("completed", False))
                checked = st.checkbox(task_label, value=is_done, key=f"task_{log_id}")
                
                if checked != is_done:
                    local_update_task_completed(log_id, checked)
                    st.toast(f"💾 タスク状態を保存しました: {task_label[:25]}... (完了: {checked})")
                    st.rerun()
                
                completed_flags.append(checked)
                
        with col_t2:
            with st.container(border=True):
                st.markdown("**今日の達成度**")
                done_count = sum(completed_flags)
                total_count = len(completed_flags)
                st.write(f"完了タスク: **{done_count} / {total_count}**")
                st.progress(done_count / total_count if total_count > 0 else 0.0)
                if done_count == total_count and total_count > 0:
                    st.success("🎉 本日の全タスク達成！素晴らしい集中力です！")
                else:
                    st.info("💡 1問終わるごとに小さな休憩を挟みましょう。")

        # ----------------------------------------------------
        # 新機能: 🌙 夜の振り返り（Daily Check-out）
        # ----------------------------------------------------
        st.markdown("---")
        st.subheader("🌙 夜の振り返り（Daily Check-out）")
        st.caption("1日の学習を締めくくり、ソクラテス先生から明日に繋がる総括フィードバックを受け取ります。")

        with st.container(border=True):
            col_co1, col_co2, col_co3 = st.columns(3)
            with col_co1:
                st.metric("本日達成タスク", f"{done_count} / {total_count} 個", delta=f"{int(done_count/total_count*100) if total_count>0 else 0}% 消化")
            with col_co2:
                st.metric("本日の実績時間", f"{total_today_hours:.1f} 時間")
            with col_co3:
                st.metric("本日獲得EXP", f"+{total_today_exp} EXP", delta="自己最高記録ペース！" if total_today_exp >= 400 else "着実な前進")

            checkout_note = st.text_area(
                "✍️ 本日の気づき・反省メモ（Focus Goldの解き応えや明日の課題など）:",
                value=local_get_meta("today_checkout_note", ""),
                placeholder="例: Focus Gold例題65の2次関数の場合分けは軸の図を描くことで完全に納得できた。明日は化学基礎のモル濃度計算から始めたい。"
            )

            saved_feedback = local_get_meta("today_checkout_feedback", "")

            if st.button("🎉 本日の学習を完了してAI終礼メッセージをもらう", type="primary", use_container_width=True):
                with st.spinner("ソクラテス先生が今日1日の学習データを総括中..."):
                    api_key = get_gemini_api_key()
                    if api_key:
                        sys_prompt = """
                        あなたは松江北高校理数科（高1）の医学部受験指導責任者・ソクラテスAIメンターです。
                        生徒が1日の学習を終えてチェックアウト（夜の振り返り）を行いました。
                        生徒の達成タスク数、実績時間、獲得EXP、および振り返りメモを読み、
                        ・今日やり遂げた努力への温かい称賛
                        ・医学部現役合格に向けた前進の評価
                        ・今夜はしっかり寝て脳に記憶を定着させるよう労う終礼メッセージ
                        を、知性と温かさに満ちた丁寧な言葉で3〜4行で述べてください。
                        """
                        prompt = f"""
                        受講生: 松江北高校理数科 1年生（医学部志望）
                        本日達成タスク: {done_count} / {total_count}
                        学習時間: {total_today_hours}時間
                        獲得EXP: {total_today_exp} EXP
                        生徒のメモ: {checkout_note}
                        """
                        ai_feedback = call_gemini(prompt, sys_prompt)
                    else:
                        ai_feedback = None

                    if not ai_feedback:
                        ai_feedback = f"""
                        **【ソクラテス先生からの終礼メッセージ】**  
                        今日1日、本当にお疲れ様でした！『{checkout_note or '計画通りの集中学習'}』という気づきを得られたことは、医学部現役合格への極めて大きな一歩です。  
                        今日獲得した **+{total_today_exp} EXP** は確実にあなたの実力になっています。寝ている間に脳が今日学んだ記憶（Focus Goldや単語）を整理して定着させますので、今夜は温かいお風呂に入ってしっかり休みましょう。明日も一緒に頑張りましょう！ 🛌✨
                        """

                    new_streak = local_checkout_today(checkout_note, ai_feedback)
                    st.toast(f"🔥 連続学習記録が {new_streak}日連続 に更新されました！")
                    st.balloons()
                    st.rerun()

            if saved_feedback:
                st.markdown("#### 🌟 ソクラテス先生からの終礼総括メッセージ")
                with st.chat_message("assistant", avatar="🧑‍🏫"):
                    st.markdown(saved_feedback)


# ==========================================
# タブ3: 🔄 弱点克服＆復習ドリル（スマホ撮影OCR ＆ NotebookLM連携）
# ==========================================
with tab3:
    st.header("🔄 弱点克服＆復習ドリル")
    st.caption("スマホ写真OCR自動登録 × Focus Gold知識検索 (NotebookLM) × Python自己検算")

    # ----------------------------------------------------
    # 新機能: 📸 スマホ写真OCR・即時弱点登録機能
    # ----------------------------------------------------
    with st.expander("📸 【スマホ撮影】間違えた問題を写真で撮って即時登録する", expanded=False):
        st.markdown("""
        スマホのカメラで間違えた問題やノートを撮影するか、アルバムから写真を選択してください。  
        **Gemini 3.6 Flash** が画像をその場で読み取り、誤答原因とヒントを抽出して弱点ドリルへ自動追加します。
        """)
        
        up_col1, up_col2 = st.columns(2)
        with up_col1:
            camera_file = st.camera_input("📷 スマホカメラで直接撮影")
        with up_col2:
            upload_file = st.file_uploader("🖼️ アルバムから写真を選択", type=["jpg", "jpeg", "png", "webp"])
            
        target_image_file = camera_file or upload_file
        
        if target_image_file is not None:
            st.image(target_image_file, caption="アップロードされた写真", width=360)
            
            if st.button("🔍 Gemini 3.6 Flash で自動OCR＆誤答分析を実行", type="primary"):
                with st.spinner("Gemini 3.6 Flash が手書き答案・数式を読み取り、誤答原因を深層分析中..."):
                    img_bytes = target_image_file.getvalue()
                    analysis_result, is_live_api = analyze_image_with_gemini_py(img_bytes, target_image_file.type)
                    
                    if is_live_api:
                        # 実際のAPIで解析成功
                        if analysis_result and not analysis_result.get("is_study_material", True):
                            st.warning(f"⚠️ {analysis_result.get('message', '勉強の問題やノートが写っていないようです。問題集やプリントを撮影してください。')}")
                        elif analysis_result:
                            st.session_state["latest_ocr_analysis"] = analysis_result
                            st.session_state["is_live_ocr"] = True
                            st.success("✅ Gemini 3.6 Flash による画像解析が完了しました！")
                    else:
                        # APIキー未設定時のシミュレーションサンプル
                        st.warning("⚠️ **Gemini APIキーが未設定のため、AIによる実際の画像認識は行われませんでした。** サイドバーにAPIキーを入力すると、本物の写真認識が動作します。（※以下はシミュレーション用のサンプル表示です）")
                        st.session_state["latest_ocr_analysis"] = {
                            "subject": "数学I・A",
                            "unit": "2次関数（Focus Gold 例題65）",
                            "topic": "文字定数を含む2次関数の区間内最大値",
                            "miss_reason": "軸 x = a が定義域の中央値より右にある場合と左にある場合で、どちらの端点が最大になるかの判定で図を描かずに解いた",
                            "hint": "放物線の対称性を思い出そう。定義域の真ん中 (p+q)/2 より軸がどちらに傾いているかで、遠い方の端点が決まります。",
                            "focus_gold_ref": "Focus Gold 数学I 例題65『2次関数の最大・最小(3)』",
                            "interval_days": 1,
                            "retention_rate": 50
                        }
                        st.session_state["is_live_ocr"] = False

        if "latest_ocr_analysis" in st.session_state:
            res = st.session_state["latest_ocr_analysis"]
            is_live_ocr = st.session_state.get("is_live_ocr", False)
            with st.container(border=True):
                if is_live_ocr:
                    st.badge("🟢 Gemini 3.6 Flash 実画像解析完了", icon="✨")
                else:
                    st.badge("🟡 シミュレーション表示（APIキー未入力）", icon="ℹ️")
                st.markdown(f"### 📋 解析結果: 【{res.get('subject')}】{res.get('topic')}")
                st.write(f"・**単元**: {res.get('unit')}")
                st.write(f"・**誤答の原因**: {res.get('miss_reason')}")
                st.write(f"・**着眼点ヒント**: {res.get('hint')}")
                st.info(f"📖 **参考書連携**: {res.get('focus_gold_ref', 'Focus Gold 該当例題を参照')}")
                
                col_save_btn, col_nb_btn = st.columns(2)
                with col_save_btn:
                    if st.button("💾 この問題を弱点ドリル（エビングハウス忘却曲線）に登録", type="primary", use_container_width=True):
                        new_wid = local_add_weakness_record(res)
                        st.toast(f"弱点問題 {new_wid} を登録しました！明日（1日後）の復習対象になります。")
                        del st.session_state["latest_ocr_analysis"]
                        st.rerun()
                with col_nb_btn:
                    nb_query_url = f"{st.session_state.get('notebooklm_url', DEFAULT_NOTEBOOKLM_URL)}"
                    st.link_button("📚 NotebookLM で解説PDFを検索", nb_query_url, use_container_width=True)

    st.markdown("---")
    
    # 忘却曲線復習アラート
    st.subheader("📚 今日の忘却曲線アラート（復習対象）")
    
    if df_weakness.empty:
        st.info("現在、復習対象の弱点データはありません。")
    else:
        w_cols = st.columns(2)
        for i, (_, row) in enumerate(df_weakness.iterrows()):
            w_id = row.get("id", f"W-{i}")
            with w_cols[i % 2]:
                with st.container(border=True):
                    retention = row.get("retention_rate", 50)
                    badge_icon = "🚨" if retention < 50 else "⚠️"
                    st.badge(f"復習サイクル: {row.get('interval_days', 1)}日目 (記憶保持率 {retention}%)", icon=badge_icon)
                    st.markdown(f"#### 【{row.get('subject', '')}】{row.get('topic', '')}")
                    st.markdown(f"**単元**: {row.get('unit', '')} | **ID**: `{w_id}` | **状態**: `{row.get('status', '復習待ち')}`")
                    st.write(f"**前回ミス内容**: {row.get('miss_reason', '')}")
                    
                    with st.expander("📝 問題・ヒント・自己評価で復習サイクルを更新"):
                        st.write(f"**ヒント・着眼点**: {row.get('hint', '')}")
                        st.link_button("📖 NotebookLMでFocus Gold類題を引く", st.session_state.get("notebooklm_url", DEFAULT_NOTEBOOKLM_URL), use_container_width=True)
                        
                        st.markdown("---")
                        st.caption("🧠 **自力で解いてみてどうでしたか？（理解度を選択すると次回復習日が自動計算されます）**")
                        ev_c1, ev_c2, ev_c3 = st.columns(3)
                        with ev_c1:
                            if st.button("🟢 完璧！自力クリア\n(+120 EXP)", key=f"btn_p_{w_id}", use_container_width=True):
                                _, _, msg = local_evaluate_weakness_review(w_id, "perfect")
                                st.toast(msg)
                                st.balloons()
                                st.rerun()
                        with ev_c2:
                            if st.button("🟡 ギリギリ/ヒント見た\n(+60 EXP)", key=f"btn_g_{w_id}", use_container_width=True):
                                _, _, msg = local_evaluate_weakness_review(w_id, "good")
                                st.toast(msg)
                                st.rerun()
                        with ev_c3:
                            if st.button("🔴 解けなかった...\n(明日再出題)", key=f"btn_h_{w_id}", use_container_width=True):
                                _, _, msg = local_evaluate_weakness_review(w_id, "hard")
                                st.toast(msg)
                                st.rerun()

    st.markdown("---")
    
    # Python自己検算ツール
    st.subheader("🧮 Python自己検算ツール（数式解析・グラフ・解の検証）")
    st.caption("手計算した答えが正しいか、Pythonを使ってその場で厳密に自己検算できます。")
    
    check_mode = st.radio("検算する対象を選択:", ["2次関数の軸・頂点・最大最小 検算", "モル計算・数値計算 検算"], horizontal=True)
    
    if check_mode == "2次関数の軸・頂点・最大最小 検算":
        st.markdown("**関数 $y = ax^2 + bx + c$ の係数と定義域を入力してください:**")
        qc1, qc2, qc3, qc4, qc5 = st.columns(5)
        with qc1:
            val_a = st.number_input("a (2次の係数)", value=1.0, step=0.5)
        with qc2:
            val_b = st.number_input("b (1次の係数)", value=-4.0, step=0.5)
        with qc3:
            val_c = st.number_input("c (定数項)", value=1.0, step=0.5)
        with qc4:
            dom_p = st.number_input("定義域 左端 p", value=0.0, step=0.5)
        with qc5:
            dom_q = st.number_input("定義域 右端 q", value=3.0, step=0.5)
            
        if val_a == 0:
            st.error("2次関数なので a は 0 以外を入力してください。")
        elif dom_p >= dom_q:
            st.error("定義域は p < q となるように入力してください。")
        else:
            vx = -val_b / (2 * val_a)
            vy = val_a * (vx ** 2) + val_b * vx + val_c
            d_val = (val_b ** 2) - 4 * val_a * val_c
            
            yp = val_a * (dom_p ** 2) + val_b * dom_p + val_c
            yq = val_a * (dom_q ** 2) + val_b * dom_q + val_c
            candidates = [(dom_p, yp), (dom_q, yq)]
            if dom_p <= vx <= dom_q:
                candidates.append((vx, vy))
            
            min_point = min(candidates, key=lambda pt: pt[1])
            max_point = max(candidates, key=lambda pt: pt[1])
            
            res_c1, res_c2 = st.columns([1, 1])
            with res_c1:
                with st.container(border=True):
                    st.markdown("**【Python厳密検算結果】**")
                    st.write(f"・**頂点座標**: `({vx:.2f}, {vy:.2f})`")
                    st.write(f"・**対称軸**: `x = {vx:.2f}`")
                    st.write(f"・**判別式 D**: `{d_val:.2f}` ({'異なる2実数解' if d_val > 0 else '重解' if d_val == 0 else '実数解なし'})")
                    st.write(f"・**区間 [{dom_p}, {dom_q}] での最小値**: `y = {min_point[1]:.2f}` (x = {min_point[0]:.2f})")
                    st.write(f"・**区間 [{dom_p}, {dom_q}] での最大値**: `y = {max_point[1]:.2f}` (x = {max_point[0]:.2f})")
            
            with res_c2:
                xs = np.linspace(min(dom_p - 1.0, vx - 1.5), max(dom_q + 1.0, vx + 1.5), 100)
                ys = val_a * (xs ** 2) + val_b * xs + val_c
                chart_df = pd.DataFrame({"x": xs, "y": ys}).set_index("x")
                st.line_chart(chart_df, height=220)
                st.caption(f"グラフ: y = {val_a}x² + ({val_b})x + ({val_c})")

    else:
        st.markdown("**化学・物理のモル計算や数式を入力して実行してください:**")
        calc_formula = st.text_input("計算式（Python数式構文）:", value="(5.6 / 22.4) * 6.02e23")
        try:
            allowed_names = {"math": math, "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "pi": math.pi}
            calc_result = eval(calc_formula, {"__builtins__": {}}, allowed_names)
            st.success(f"**検算結果**: `{calc_result}`")
        except Exception as e:
            st.error(f"数式エラー: {e}")

    st.markdown("---")
    
    # ファインマンモード解法説明フォーム
    st.subheader("🧠 ファインマンモード（解法説明アウトプット × AI採点）")
    st.info("💡 **ファインマン・テクニック**: 「中学生にも理解できるように、専門用語を使わずに自分の言葉で説明できれば、本質を理解した証拠である」という学習法です。Geminiがあなたの解説をリアルタイム採点します。")
    
    topics_from_db = df_weakness["topic"].tolist() if not df_weakness.empty and "topic" in df_weakness.columns else [
        "【数学】文字定数を含む2次関数の最大・最小の場合分けの考え方"
    ]
    feynman_topic = st.selectbox("本日の解説テーマを選択してください:", topics_from_db)
    
    user_explanation = st.text_area(
        "あなたの言葉で解説を入力してください（数式丸暗記ではなく、背景にある理由やイメージを記述）:",
        height=140,
        placeholder="例: 2次関数の場合分けは、放物線の軸が動くときに『見たい窓（定義域）』の中に頂点が入っているかどうかで..."
    )
    
    if st.button("📤 AIソクラテスに説明を提出・採点してもらう", type="primary"):
        if user_explanation.strip():
            with st.spinner("Gemini AIが論理展開と本質理解度を分析・採点中..."):
                gemini_key = get_gemini_api_key()
                if gemini_key:
                    sys_prompt = """
                    あなたは最高峰の医学部受験指導者兼ファインマン学習法の審査員です。
                    生徒（高校1年生）が「専門用語を噛み砕いて自分の言葉で解説した文章」を審査します。
                    【出力フォーマット】
                    1. 🎯 本質理解度スコア: XX / 100点
                    2. 良かった点（直感的な比喩や平易な言葉遣い）
                    3. 改善点・補足すべき論点（高校数学/理科として答案にする際の注意点）
                    4. 医学部合格に向けたワンポイントアドバイス
                    """
                    prompt = f"解説テーマ: {feynman_topic}\n生徒の解説: {user_explanation}"
                    feedback = call_gemini(prompt, sys_prompt)
                else:
                    feedback = None
                
                if feedback:
                    st.success("🎯 Gemini AIによるリアルタイム採点が完了しました！")
                    with st.chat_message("assistant", avatar="🧑‍🏫"):
                        st.markdown(feedback)
                else:
                    st.success("🎯 採点完了！本質理解度スコア: **95 / 100点** (シミュレーション)")
                    with st.chat_message("assistant", avatar="🧑‍🏫"):
                        st.markdown("""
                        **【AIメンターからの講評】**  
                        - **Good**: 「定義域の窓」という直感的な比喩を使って、軸が定義域の左・中央・右のどこにあるかで最大最小が決まる原理を平易に説明できています！
                        - **Next Step**: 「境界となる等号（≦ または ≧）はどちらに含めても結果は同じになる」という一言を添えると、記述答案としても完全無欠です。
                        """)
        else:
            st.warning("解説を入力してから提出ボタンを押してください。")

    st.markdown("---")

    # ----------------------------------------------------
    # 新機能: 🖨️ 週末弱点総復習テスト（A4印刷・まとめ出力モード）
    # ----------------------------------------------------
    st.subheader("🖨️ 週末弱点総復習テスト（A4印刷・まとめ出力モード）")
    st.caption("忘却曲線DBに蓄積された弱点から、週末の自己測定用ペーパーを一括生成します。紙とペンで制限時間を測って解くことで、医学部入試で求められる『白紙からの再現力』を鍛えます。")

    t_filter_col1, t_filter_col2, t_filter_col3 = st.columns([1.5, 1.5, 1])
    with t_filter_col1:
        test_scope = st.selectbox(
            "📋 出題範囲:",
            ["復習待ち・要復習のみ（推奨）", "弱点DBの全問題（総ざらい）"],
            index=0
        )
    with t_filter_col2:
        available_subjects = ["すべての科目"] + sorted(list(set(df_weakness["subject"].dropna().tolist()))) if not df_weakness.empty and "subject" in df_weakness.columns else ["すべての科目", "数学I・A", "化学基礎", "物理基礎"]
        selected_subject_filter = st.selectbox("🎯 対象科目:", available_subjects, index=0)
    with t_filter_col3:
        include_hint_mode = st.selectbox("💡 ヒント表示:", ["折りたたみ（自力演習用）", "テスト用紙に記載"], index=0)

    # フィルタリング
    target_test_df = df_weakness.copy() if not df_weakness.empty else pd.DataFrame()
    if not target_test_df.empty:
        if test_scope == "復習待ち・要復習のみ（推奨）" and "status" in target_test_df.columns:
            target_test_df = target_test_df[target_test_df["status"].isin(["復習待ち", "要復習 🚨", "要復習"])]
            if target_test_df.empty:
                # 復習待ちがゼロの場合は全件からフォールバック
                target_test_df = df_weakness.copy()
        if selected_subject_filter != "すべての科目" and "subject" in target_test_df.columns:
            target_test_df = target_test_df[target_test_df["subject"] == selected_subject_filter]

    st.write(f"📝 現在の該当問題数: **{len(target_test_df)} 問**（目安制限時間: {max(len(target_test_df)*15, 15)} 分）")

    if st.button("📄 週末復習テスト用紙を自動生成する", type="primary", use_container_width=True):
        st.session_state["show_weekend_test"] = True

    if st.session_state.get("show_weekend_test", False):
        if target_test_df.empty:
            st.info("出題対象の弱点問題がありません。まずは上のカメラ登録や忘却曲線ドリルで弱点を記録しましょう。")
        else:
            with st.container(border=True):
                # 印刷コントロールヘッダー
                p_c1, p_c2 = st.columns([2, 1])
                with p_c1:
                    st.markdown("### 📄 松江北高校 理数科 医学部現役合格特訓 【週末弱点総復習テスト】")
                    st.caption(f"実施日: {datetime.date.today().strftime('%Y年%m月%d日')} ｜ 目安時間: {len(target_test_df)*15}分 ｜ 配点: 1問25点 (計 {len(target_test_df)*25}点満点)")
                with p_c2:
                    st.markdown("""
                    <div style="text-align: right; padding-top: 5px;">
                        <button onclick="window.print()" style="background-color: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold;">
                            🖨️ ブラウザ印刷 (Cmd+P)
                        </button>
                    </div>
                    """, unsafe_allow_html=True)
                    st.caption("※Macでは `Cmd + P` でPDF保存・A4印刷が可能です。")

                st.divider()

                # テスト問題のマークダウン生成
                markdown_test_content = f"# 松江北高校 理数科 医学部現役合格特訓 【週末弱点総復習テスト】\n"
                markdown_test_content += f"実施日: {datetime.date.today().strftime('%Y-%m-%d')} | 受講生: 松江北高1年（医学部志望） | 目標: 満点再現\n\n---\n\n"

                for q_idx, (_, q_row) in enumerate(target_test_df.iterrows(), start=1):
                    qid = q_row.get("id", f"Q-{q_idx}")
                    sub = q_row.get("subject", "科目")
                    unit = q_row.get("unit", "単元")
                    topic = q_row.get("topic", "問題テーマ")
                    miss = q_row.get("miss_reason", "誤答原因")
                    hint = q_row.get("hint", "定義に立ち返って整理しよう")
                    cycle = q_row.get("interval_days", 1)

                    st.markdown(f"#### 【第 {q_idx} 問】 [{sub}] {unit} — `{qid}`")
                    st.markdown(f"**◆ 設問テーマ**: **{topic}**")
                    st.markdown(f"**◆ 過去の誤答トラップ**: `{miss}`")
                    
                    if include_hint_mode == "テスト用紙に記載":
                        st.info(f"💡 **着眼点ヒント**: {hint}")
                    else:
                        with st.expander(f"💡 第{q_idx}問のヒント（解き終わった後に確認）"):
                            st.write(f"**着眼点**: {hint}")
                            st.caption(f"エビングハウス復習間隔: {cycle}日目 サイクル")

                    # 解答用紙スペース（ノート罫線風）
                    st.markdown("""
                    <div style="border: 2px dashed #94a3b8; border-radius: 8px; padding: 25px; margin: 15px 0; background-color: #f8fafc; min-height: 140px; color: #64748b;">
                        <em>【思考プロセス・立式・記述解答スペース】</em><br><br>
                        <span style="font-size: 0.85em; color: #94a3b8;">※医学部入試を意識し、論理の飛躍がないように日本語と数式を丁寧に記述してください。</span>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown("---")

                    markdown_test_content += f"### 【第 {q_idx} 問】 [{sub}] {unit} ({qid})\n"
                    markdown_test_content += f"- **出題論点**: {topic}\n"
                    markdown_test_content += f"- **過去の誤答トラップ**: {miss}\n"
                    markdown_test_content += f"- **着眼点ヒント**: {hint}\n\n"
                    markdown_test_content += "【解答欄】\n\n\n\n---\n\n"

                col_dl, col_close = st.columns([2, 1])
                with col_dl:
                    st.download_button(
                        label="📥 テスト用紙（Markdownファイル）をダウンロード",
                        data=markdown_test_content,
                        file_name=f"weekend_test_{datetime.date.today().strftime('%Y%m%d')}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                with col_close:
                    if st.button("❌ テスト表示を閉じる", use_container_width=True):
                        st.session_state["show_weekend_test"] = False
                        st.rerun()


# ==========================================
# タブ4: 📈 全体ロードマップ（バーンダウンチャート付き）
# ==========================================
with tab4:
    st.header("📈 全体ロードマップ＆進捗分析")
    st.caption("テスト・模試へのカウントダウン × 学習時間バーンダウンチャート（残時間消化推移）")
    
    st.subheader("⏳ 入試・模試カウントダウン")
    exams = df_roadmap[df_roadmap["category"] == "exam"] if not df_roadmap.empty and "category" in df_roadmap.columns else pd.DataFrame()
    if not exams.empty:
        exam_cols = st.columns(min(len(exams), 4))
        for idx, (_, row) in enumerate(exams.head(4).iterrows()):
            with exam_cols[idx]:
                try:
                    target_dt = datetime.datetime.strptime(str(row["target_date"]), "%Y-%m-%d").date()
                    delta_days = (target_dt - datetime.date.today()).days
                    delta_text = f"あと {delta_days} 日" if delta_days >= 0 else f"{abs(delta_days)} 日経過"
                except Exception:
                    delta_text = "日程未定"
                st.metric(label=row.get("title", ""), value=delta_text, delta=row.get("progress_or_score", ""))
    
    st.markdown("---")
    
    st.subheader("📉 模試・期末テスト目標消化 バーンダウンチャート")
    st.caption("目標時間（70時間スプリント）に対する『理想消化ペース（Ideal）』と『実際の残り時間推移（Actual）』の比較です。線が理想線より下にあれば前倒しで進んでいます！")
    
    total_sprint_target = 70.0
    sprint_days = 14
    ideal_per_day = total_sprint_target / sprint_days
    
    dates = []
    ideal_remaining = []
    actual_remaining = []
    
    past_accumulated = 0.0
    for day_offset in range(7, 0, -1):
        dt = (datetime.date.today() - datetime.timedelta(days=day_offset))
        dt_str = dt.strftime("%m/%d")
        dates.append(dt_str)
        
        day_index = 7 - day_offset
        ideal_rem = max(total_sprint_target - (day_index * ideal_per_day), 0.0)
        ideal_remaining.append(round(ideal_rem, 1))
        
        past_accumulated += 5.5 + (0.5 if day_offset % 2 == 0 else -0.3)
        actual_rem = max(total_sprint_target - past_accumulated, 0.0)
        actual_remaining.append(round(actual_rem, 1))
        
    today_dt_str = datetime.date.today().strftime("%m/%d")
    dates.append(today_dt_str)
    ideal_remaining.append(round(max(total_sprint_target - (7 * ideal_per_day), 0.0), 1))
    today_actual_rem = max(total_sprint_target - (past_accumulated + total_today_hours), 0.0)
    actual_remaining.append(round(today_actual_rem, 1))
    
    for future_offset in range(1, 8):
        dt = (datetime.date.today() + datetime.timedelta(days=future_offset))
        dt_str = dt.strftime("%m/%d")
        dates.append(dt_str)
        day_index = 7 + future_offset
        ideal_rem = max(total_sprint_target - (day_index * ideal_per_day), 0.0)
        ideal_remaining.append(round(ideal_rem, 1))
        actual_remaining.append(None)
        
    burndown_df = pd.DataFrame({
        "日付": dates,
        "理想ペース線 (Ideal)": ideal_remaining,
        "実際の残り時間 (Actual)": actual_remaining
    }).set_index("日付")
    
    st.line_chart(burndown_df)
    
    diff = ideal_remaining[7] - actual_remaining[7]
    if diff >= 0:
        st.success(f"🔥 **好調ペース**: 計画より `{diff:.1f} 時間` 前倒しでタスクを消化中！このペースを維持すれば駿台模試で学年トップ層を狙えます。")
    else:
        st.warning(f"⚠️ **ペース調整推奨**: 計画より `{abs(diff):.1f} 時間` 遅れ気味です。週末の作戦会議で調整時間を確保しましょう。")
    
    st.markdown("---")
    
    st.subheader("📖 科目別・合格目標到達度（高1理数科カリキュラム）")
    subjects = df_roadmap[df_roadmap["category"] == "subject"] if not df_roadmap.empty and "category" in df_roadmap.columns else pd.DataFrame()
    
    if not subjects.empty:
        subj_cols = st.columns(2)
        for idx, (_, row) in enumerate(subjects.iterrows()):
            with subj_cols[idx % 2]:
                try:
                    pct = float(row.get("progress_or_score", 0)) / 100.0
                except ValueError:
                    pct = 0.5
                st.write(f"**{row.get('title', '')}**: {int(pct * 100)}% ({row.get('memo', '')})")
                st.progress(min(max(pct, 0.0), 1.0))

    st.markdown("---")
    
    # ----------------------------------------------------
    # 新機能: 📊 模試・定期テスト成績管理 ＆ 医学部合格ギャップ分析
    # ----------------------------------------------------
    st.subheader("📊 模試・定期テスト成績推移 ＆ 医学部合格ギャップ分析")
    st.caption("国公立大医学部医学科の現役合格ボーダー（全国偏差値 68.0 / 校内トップ5）に対する現在地と教科別ギャップを追跡します。")
    
    df_exams = local_get_exam_records()
    MED_BORDER = 68.0
    
    if not df_exams.empty:
        latest_exam = df_exams.iloc[-1]
        cur_total = latest_exam["total_dev"]
        cur_math = latest_exam["math_dev"]
        cur_eng = latest_exam["eng_dev"]
        cur_sci = latest_exam["sci_dev"]
        
        # ギャップメトリクス
        gap_total = round(cur_total - MED_BORDER, 1)
        gap_math = round(cur_math - MED_BORDER, 1)
        gap_eng = round(cur_eng - MED_BORDER, 1)
        gap_sci = round(cur_sci - MED_BORDER, 1)
        
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        with m_c1:
            st.metric("直近 総合偏差値", f"{cur_total:.1f}", delta=f"{'+' if gap_total>=0 else ''}{gap_total} (ボーダー68)")
        with m_c2:
            st.metric("数学偏差値", f"{cur_math:.1f}", delta=f"{'+' if gap_math>=0 else ''}{gap_math} (武器)")
        with m_c3:
            st.metric("理科偏差値", f"{cur_sci:.1f}", delta=f"{'+' if gap_sci>=0 else ''}{gap_sci} (合格圏)")
        with m_c4:
            st.metric("英語偏差値", f"{cur_eng:.1f}", delta=f"{'+' if gap_eng>=0 else ''}{gap_eng} (要強化)")

        # 偏差値推移グラフ
        chart_exams = df_exams.copy()
        chart_exams["医学部ボーダー線"] = MED_BORDER
        chart_df = chart_exams[["date", "math_dev", "eng_dev", "sci_dev", "total_dev", "医学部ボーダー線"]].rename(columns={
            "math_dev": "数学",
            "eng_dev": "英語",
            "sci_dev": "理科",
            "total_dev": "総合"
        }).set_index("date")
        
        st.line_chart(chart_df)
        
        # 直近テストの講評＆順位
        with st.container(border=True):
            st.markdown(f"#### 🏆 直近結果: 『{latest_exam['exam_name']}』({latest_exam['date']})")
            st.write(f"・**校内順位**: `{latest_exam['school_rank']}`")
            st.write(f"・**学習成果メモ**: {latest_exam['memo']}")
            if gap_total >= 0:
                st.success(f"🎉 **医学部合格圏内**: 総合偏差値がボーダー（68.0）を上回っています！特に数学（偏差値{cur_math}）のリードを維持しつつ、英語（偏差値{cur_eng}）を68に乗せれば盤石のA判定が見えてきます。")
            else:
                st.warning(f"⚠️ **ボーダーまであと {abs(gap_total)}**: 英語・理科の基礎論点を固めることで、十分合格圏内へ浮上できるポジションです。")

    # 成績新規登録フォーム
    with st.expander("➕ 新しい模試・定期テストの成績を記録する"):
        with st.form("add_exam_form"):
            in_name = st.text_input("模試・テスト名:", placeholder="例: 第2回 駿台高1全国模試")
            in_date = st.date_input("実施日:", value=datetime.date.today())
            ec1, ec2, ec3, ec4 = st.columns(4)
            with ec1:
                in_math = st.number_input("数学 偏差値:", value=68.0, step=0.5)
            with ec2:
                in_eng = st.number_input("英語 偏差値:", value=65.0, step=0.5)
            with ec3:
                in_sci = st.number_input("理科 偏差値:", value=67.0, step=0.5)
            with ec4:
                in_tot = st.number_input("総合 偏差値:", value=67.0, step=0.5)
            in_rank = st.text_input("順位:", placeholder="例: 理数科 5位 / 学年 9位")
            in_memo = st.text_area("反省・成果メモ:", placeholder="例: 数学はFocus Gold類題が完答できた。英語の長文読解速度が課題。")
            
            if st.form_submit_button("💾 成績を保存してグラフに反映"):
                if in_name.strip():
                    local_add_exam_record(in_name, in_date.strftime("%Y-%m-%d"), in_math, in_eng, in_sci, in_tot, in_rank, in_memo)
                    st.toast(f"『{in_name}』の成績を記録しました！")
                    st.rerun()
                else:
                    st.warning("テスト名を入力してください。")

    st.markdown("---")

    # ----------------------------------------------------
    # 新機能: 📚 Focus Gold ＆ 理科 単元別マスター進捗マップ
    # ----------------------------------------------------
    st.subheader("📚 Focus Gold ＆ 理科 単元別マスター進捗マップ")
    st.caption("松江北高校 理数科カリキュラム × 医学部現役合格に必要な全単元（数I・A、先取り数II・B、物理基礎、化学基礎）の習得状況を網羅管理します。Focus Gold例題・類題をマスターしたらチェックを入れましょう。")

    df_all_units = local_get_unit_progress()

    if not df_all_units.empty:
        # 全体メトリクス
        total_units_count = len(df_all_units)
        fg_mastered_count = int(df_all_units["focus_gold_ok"].sum())
        overall_pct = (fg_mastered_count / total_units_count) if total_units_count > 0 else 0.0

        u_m1, u_m2, u_m3 = st.columns([1, 2, 1])
        with u_m1:
            st.metric("総単元マスター数", f"{fg_mastered_count} / {total_units_count} 単元", delta=f"{int(overall_pct * 100)}% 完了")
        with u_m2:
            st.write(f"**全科目総合 Focus Gold 網羅率**: `{int(overall_pct * 100)}%`")
            st.progress(overall_pct)
        with u_m3:
            st.badge("医学部現役合格目安: 高1末までに60%以上", icon="🎯")

        st.markdown("<br>", unsafe_allow_html=True)

        # 科目別タブ
        u_tab_math1, u_tab_math2, u_tab_phys, u_tab_chem = st.tabs([
            "📐 数学I・A",
            "🚀 数学II・B 先取り",
            "⚡ 物理基礎",
            "🧪 化学基礎"
        ])

        subject_tab_pairs = [
            ("数学I・A", u_tab_math1, "Focus Gold 数学I+A 完全制覇"),
            ("数学II・B 先取り", u_tab_math2, "理数科アドバンテージ Focus Gold II+B"),
            ("物理基礎", u_tab_phys, "物理のエッセンス・定期テスト満点"),
            ("化学基礎", u_tab_chem, "モル計算・酸塩基・酸化還元マスター")
        ]

        status_options = ["未着手 ⚪", "学習中 🟡", "一通り完了 🔵", "Focus Goldマスター 🎓"]

        for subj_name, target_tab, target_sub_desc in subject_tab_pairs:
            with target_tab:
                subj_df = df_all_units[df_all_units["subject"] == subj_name]
                s_total = len(subj_df)
                s_master = int(subj_df["focus_gold_ok"].sum()) if not subj_df.empty else 0
                s_pct = (s_master / s_total) if s_total > 0 else 0.0

                c_info1, c_info2 = st.columns([3, 1])
                with c_info1:
                    st.markdown(f"#### {subj_name} — {target_sub_desc}")
                    st.progress(s_pct)
                with c_info2:
                    st.metric("マスター率", f"{s_master} / {s_total} 単元", delta=f"{int(s_pct*100)}%")

                st.markdown("---")

                if subj_df.empty:
                    st.info(f"{subj_name} の単元データがまだありません。")
                else:
                    for _, u_row in subj_df.iterrows():
                        uid = int(u_row["id"])
                        uname = str(u_row["unit_name"])
                        ustatus = str(u_row["status"])
                        ufg = bool(u_row["focus_gold_ok"])

                        col_u1, col_u2, col_u3 = st.columns([3, 2, 1.5])
                        with col_u1:
                            st.write(f"**{uname}**")
                            st.caption(f"最終更新: {u_row.get('updated_at', '-')}")
                        with col_u2:
                            current_idx = status_options.index(ustatus) if ustatus in status_options else 0
                            new_status = st.selectbox(
                                "ステータス",
                                status_options,
                                index=current_idx,
                                key=f"status_sel_{uid}",
                                label_visibility="collapsed"
                            )
                        with col_u3:
                            new_fg = st.checkbox(
                                "FGマスター 🎓",
                                value=ufg,
                                key=f"fg_chk_{uid}"
                            )

                        if new_status != ustatus or new_fg != ufg:
                            local_update_unit_progress(uid, new_status, new_fg)
                            st.toast(f"💾 『{uname}』の状態を更新しました！（{new_status}）")
                            st.rerun()

                        st.markdown("<hr style='margin: 4px 0; border: none; border-top: 1px dashed #e2e8f0;'>", unsafe_allow_html=True)

        # 単元手動追加フォーム
        with st.expander("➕ 新しい単元・特訓論点をリストに追加する"):
            with st.form("add_unit_form"):
                a_sub = st.selectbox("科目:", ["数学I・A", "数学II・B 先取り", "物理基礎", "化学基礎"])
                a_name = st.text_input("単元名・論点名:", placeholder="例: 共通テスト特訓 確率漸化式")
                a_stat = st.selectbox("初期状態:", status_options)
                a_fg = st.checkbox("Focus Goldマスター済み")
                if st.form_submit_button("💾 単元を追加する"):
                    if a_name.strip():
                        local_add_unit_progress(a_sub, a_name.strip(), a_stat, a_fg)
                        st.toast(f"『{a_name}』を追加しました！")
                        st.rerun()
                    else:
                        st.warning("単元名を入力してください。")


# ==========================================
# タブ5: 💬 24時間質問部屋
# ==========================================
with tab5:
    st.header("💬 24時間質問部屋（ソクラテス式AI対話 × 自動対話保存）")
    st.caption("AIは安易に答えを教えません。対話と発問を通じて、あなた自身が解答の糸口を掴めるようアシストします。会話は自動保存されます。")
    
    chat_logs = local_get_chat_history()
    
    for msg in chat_logs:
        avatar = "🧑‍🎓" if msg["role"] == "user" else "🏛️"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            
    if user_prompt := st.chat_input("質問や考えを入力してください（例: 真ん中は1だから、頂点が1より左なら右端のほうが遠くなる…？）"):
        local_add_chat_message("user", user_prompt)
        with st.chat_message("user", avatar="🧑‍🎓"):
            st.markdown(user_prompt)
            
        with st.spinner("ソクラテス先生が考え中..."):
            gemini_key = get_gemini_api_key()
            if gemini_key:
                socrates_system_instruction = """
                あなたは「ソクラテス式AI学習メンター」です。
                受講生は松江北高校 理数科の高校1年生で、将来国公立大学医学部医学科を目指しています。
                【指導方針】
                1. 絶対に直接的な正解や計算結果を教えてはいけません。
                2. 生徒の着眼点や努力を認めつつ、「なぜそうなると思う？」「基本の定義は何だった？」といった思考を促す問いかけ（発問）や直感的なアナロジー（比喩）を投げかけてください。
                3. 必要に応じて「Focus Goldの該当例題を見てごらん」といった自走のヒントを与えてください。
                4. 口調は温かく、知性と敬意に満ちた丁寧語で話してください。
                """
                recent_history = "\n".join([f"{m['role']}: {m['content']}" for m in chat_logs[-4:]])
                prompt = f"これまでの対話:\n{recent_history}\n生徒の最新の発言: {user_prompt}\nソクラテスメンターとしての返答:"
                response = call_gemini(prompt, socrates_system_instruction)
            else:
                response = None

            if not response:
                response = f"その着眼点、素晴らしいですね！「{user_prompt}」という気付きがまさに本質です。軸と定義域の中心の位置関係を考えると、どちらの端点がより遠くなるかが一目瞭然ですね。Focus Gold の例題65の図とも照らし合わせてみましょう！"
            
            local_add_chat_message("assistant", response)
            with st.chat_message("assistant", avatar="🏛️"):
                st.markdown(response)
                
            st.rerun()
