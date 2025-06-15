from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from database import get_conn, release_conn

async def colleagues_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT e.last_name, e.first_name
        FROM employees e
        JOIN online_status o ON e.id = o.employee_id
        WHERE o.is_online=TRUE
          AND e.department_id = (SELECT department_id FROM employees WHERE telegram_id=%s)
          AND e.division_id   = (SELECT division_id   FROM employees WHERE telegram_id=%s);
    """, (user.id, user.id))
    rows = cur.fetchall()
    release_conn(conn)
    if not rows:
        text = "Сейчас никто из ваших коллег не в сети."
    else:
        text = "Коллеги в сети:\n" + "\n".join(f"{ln} {fn}" for ln, fn in rows)
    await update.message.reply_text(text)
