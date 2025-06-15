from telegram import Update
from telegram.ext import ContextTypes
from database import get_conn, release_conn
import datetime


async def stats_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COALESCE(SUM(EXTRACT(EPOCH FROM duration)), 0)
        FROM work_sessions
        WHERE employee_id = (
            SELECT id FROM employees WHERE telegram_id = %s
        )
          AND DATE(started_at) = CURRENT_DATE
          AND duration IS NOT NULL;
        """,
        (user.id,)
    )
    today_secs = cur.fetchone()[0] or 0

    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())

    cur.execute(
        """
        SELECT DATE(started_at) AS day, SUM(EXTRACT(EPOCH FROM duration)) AS secs
        FROM work_sessions
        WHERE employee_id = (
            SELECT id FROM employees WHERE telegram_id = %s
        )
          AND DATE(started_at) BETWEEN %s AND CURRENT_DATE
          AND duration IS NOT NULL
        GROUP BY day;
        """,
        (user.id, monday)
    )
    week_rows = cur.fetchall()

    first_of_month = today.replace(day=1)
    cur.execute(
        """
        SELECT DATE(started_at) AS day, SUM(EXTRACT(EPOCH FROM duration)) AS secs
        FROM work_sessions
        WHERE employee_id = (
            SELECT id FROM employees WHERE telegram_id = %s
        )
          AND DATE(started_at) BETWEEN %s AND CURRENT_DATE
          AND duration IS NOT NULL
        GROUP BY day;
        """,
        (user.id, first_of_month)
    )
    month_rows = cur.fetchall()

    release_conn(conn)

    def fmt(sec):
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        return f"{h}ч {m}м"

    week_secs = [row[1] for row in week_rows]
    week_avg = sum(week_secs) / len(week_secs) if week_secs else 0

    month_secs = [row[1] for row in month_rows]
    month_avg = sum(month_secs) / len(month_secs) if month_secs else 0

    text = (
        f"Отработано сегодня: {fmt(today_secs)}\n"
        f"Среднее время работы за неделю: {fmt(week_avg)}\n"
        f"Среднее время работы за месяц: {fmt(month_avg)}"
    )
    await update.message.reply_text(text)
