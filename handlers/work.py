from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from database import get_conn, release_conn
import datetime
from models import get_employee_by_telegram
from models import start_work_session, end_work_session


def work_keyboard(is_admin: bool = False):
    kb = [
        [KeyboardButton("Начал"), KeyboardButton("Закончил")],
        [KeyboardButton("Отошел"), KeyboardButton("Вернулся")],
        [KeyboardButton("Коллеги"), KeyboardButton("Статистика")],
        [KeyboardButton("Напоминания")],
    ]
    if is_admin:
        kb.append([KeyboardButton("Дать админ"), KeyboardButton("Удалить")])
        kb.append([KeyboardButton("Отчёты")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    emp = get_employee_by_telegram(user_id)
    is_admin = (emp and emp[1] == 'admin')
    kb = work_keyboard(is_admin=is_admin)
    text = "Выберите действие:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

def _get_user_state(conn, telegram_id):
    cur = conn.cursor()
    cur.execute("SELECT is_online FROM online_status o JOIN employees e ON o.employee_id=e.id WHERE e.telegram_id=%s;", (telegram_id,))
    is_online = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM breaks b JOIN work_sessions w ON b.session_id=w.id JOIN employees e ON w.employee_id=e.id WHERE e.telegram_id=%s AND w.ended_at IS NULL AND b.ended_at IS NULL;", (telegram_id,))
    in_break = cur.fetchone()[0] > 0
    cur.execute("SELECT COUNT(*) FROM work_sessions w JOIN employees e ON w.employee_id=e.id WHERE e.telegram_id=%s AND w.ended_at IS NULL;", (telegram_id,))
    has_session = cur.fetchone()[0] > 0
    return is_online, has_session, in_break

async def start_work_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Начал":
        return
    user = update.message.from_user
    conn = get_conn()
    is_online, has_session, in_break = _get_user_state(conn, user.id)
    if is_online or has_session:
        await update.message.reply_text(
            "Нельзя начать работу: у Вас уже активная сессия или Вы уже в онлайне. Сначала завершите её.")
        release_conn(conn)
        return
    ts = datetime.datetime.now()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO work_sessions (employee_id, started_at)
        VALUES ((SELECT id FROM employees WHERE telegram_id=%s), %s)
    """, (user.id, ts))
    cur.execute("UPDATE online_status SET is_online=TRUE, updated_at=%s WHERE employee_id=(SELECT id FROM employees WHERE telegram_id=%s);", (ts, user.id))
    conn.commit(); release_conn(conn)
    await update.message.reply_text("Начало рабочего дня зафиксировано.")

async def end_work_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Закончил":
        return
    user = update.message.from_user
    conn = get_conn()
    is_online, has_session, in_break = _get_user_state(conn, user.id)
    if not has_session or not is_online or in_break:
        await update.message.reply_text("Нельзя закончить работу: либо Вы не начали сессию, либо сейчас перерыв.")
        release_conn(conn)
        return
    ts = datetime.datetime.now()
    cur = conn.cursor()
    cur.execute("""
        UPDATE work_sessions
        SET duration = %s - started_at,
            ended_at = %s
        WHERE employee_id = (
            SELECT id FROM employees WHERE telegram_id = %s
        )
          AND ended_at IS NULL
    """, (ts, ts, user.id))
    cur.execute(
        "UPDATE online_status "
        "SET is_online = FALSE, updated_at = %s "
        "WHERE employee_id = (SELECT id FROM employees WHERE telegram_id = %s);",
        (ts, user.id)
    )
    conn.commit()
    release_conn(conn)
    await update.message.reply_text("Окончание рабочего дня зафиксировано.")


async def start_break_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Отошел":
        return
    user = update.message.from_user
    conn = get_conn()
    is_online, has_session, in_break = _get_user_state(conn, user.id)
    if not has_session or not is_online or in_break:
        await update.message.reply_text("Нельзя начать перерыв: либо нет активной сессии, либо уже на перерыве.")
        release_conn(conn)
        return
    ts = datetime.datetime.now()
    cur = conn.cursor()
    cur.execute("SELECT id FROM work_sessions WHERE employee_id=(SELECT id FROM employees WHERE telegram_id=%s) AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1;", (user.id,))
    session_id = cur.fetchone()[0]
    cur.execute("INSERT INTO breaks (session_id, started_at) VALUES (%s, %s);", (session_id, ts))
    cur.execute("UPDATE online_status SET is_online=FALSE, updated_at=%s WHERE employee_id=(SELECT id FROM employees WHERE telegram_id=%s);", (ts, user.id))
    conn.commit(); release_conn(conn)
    await update.message.reply_text("Начало перерыва зафиксировано.")

async def end_break_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "Вернулся":
        return
    user = update.message.from_user
    conn = get_conn()
    is_online, has_session, in_break = _get_user_state(conn, user.id)
    if not in_break:
        await update.message.reply_text("Нельзя закончить перерыв: Вы не на перерыве.")
        release_conn(conn)
        return
    ts = datetime.datetime.now()
    cur = conn.cursor()
    cur.execute("""
        UPDATE breaks
        SET ended_at = %s,
            duration = %s - started_at
        WHERE id = (
            SELECT b.id
            FROM breaks b
            JOIN work_sessions w ON b.session_id = w.id
            WHERE w.employee_id = (
                SELECT id FROM employees WHERE telegram_id = %s
            )
              AND b.ended_at IS NULL
            ORDER BY b.started_at DESC
            LIMIT 1
        )
    """, (ts, ts, user.id))
    cur.execute(
        "UPDATE online_status "
        "SET is_online = TRUE, updated_at = %s "
        "WHERE employee_id = (SELECT id FROM employees WHERE telegram_id = %s);",
        (ts, user.id)
    )
    conn.commit(); release_conn(conn)
    await update.message.reply_text("Конец перерыва зафиксирован.")