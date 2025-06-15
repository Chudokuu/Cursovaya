from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import datetime
from io import BytesIO
import pandas as pd
from models import get_employee_by_telegram
from database import get_conn, release_conn


(
    ASK_START_DATE,
    ASK_END_DATE,
    CHOOSE_FORMAT,
    GENERATE_REPORT,
) = range(4)

REPORT_STATES = {
    "ASK_START": ASK_START_DATE,
    "ASK_END": ASK_END_DATE,
    "CHOOSE_FORMAT": CHOOSE_FORMAT,
}

report_temp = {}

async def reports_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message
    user = query.from_user
    emp = get_employee_by_telegram(user.id)
    if not emp or emp[1] != "admin":  # emp = (id, role, dep, div)
        await query.reply_text("У вас нет прав администратора.")
        return ConversationHandler.END

    await query.reply_text(
        "Введите начальную дату отчёта в формате YYYY-MM-DD, например: 2025-06-01"
    )
    return ASK_START_DATE

async def ask_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        start_date = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Неверный формат. Введите ещё раз дату в формате YYYY-MM-DD.")
        return ASK_START_DATE

    report_temp["start_date"] = start_date
    await update.message.reply_text("Введите конечную дату отчёта (YYYY-MM-DD), например: 2025-06-30")
    return ASK_END_DATE

async def choose_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        end_date = datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("Неверный формат. Введите ещё раз дату в формате YYYY-MM-DD.")
        return ASK_END_DATE

    start_date = report_temp.get("start_date")
    if end_date < start_date:
        await update.message.reply_text("Дата окончания ранее даты начала. Попробуйте ещё раз.")
        return ASK_END_DATE

    report_temp["end_date"] = end_date

    buttons = [
        [InlineKeyboardButton("Текстовый отчёт", callback_data="format_text")],
        [InlineKeyboardButton("Excel-файл", callback_data="format_excel")],
        [InlineKeyboardButton("Отмена", callback_data="cancel_report")],
    ]
    await update.message.reply_text("Выберите формат отчёта:", reply_markup=InlineKeyboardMarkup(buttons))
    return CHOOSE_FORMAT

def _format_timedelta_to_hours_minutes(td: datetime.timedelta) -> str:
    if isinstance(td, float) or isinstance(td, (int,)):
        total_seconds = int(td * 3600)
    else:
        total_seconds = int(td.total_seconds())

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours} ч. {minutes:02d} мин."

async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_report":
        await query.edit_message_text("Формирование отчёта отменено.")
        return ConversationHandler.END

    start_date = report_temp.get("start_date")
    end_date = report_temp.get("end_date")
    user = query.from_user
    emp = get_employee_by_telegram(user.id)
    employee_id, role, dep_id, div_id = emp

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            e.id,
            e.last_name || ' ' || e.first_name AS full_name,
            SUM(EXTRACT(EPOCH FROM ws.duration))/3600 AS total_hours,
            e.overtime,
            COUNT(DISTINCT ws.started_at::date) AS shifts_count
        FROM work_sessions ws
        JOIN employees e ON ws.employee_id = e.id
        WHERE ws.started_at::date BETWEEN %s AND %s
          AND ws.duration IS NOT NULL
          AND e.department_id = %s
          AND e.division_id = %s
        GROUP BY e.id, full_name, e.overtime
        ORDER BY full_name;
        """,
        (start_date, end_date, dep_id, div_id),
    )
    rows = cur.fetchall()
    release_conn(conn)

    if data == "format_text":
        if not rows:
            text = f"За период {start_date} — {end_date} данных не найдено."
        else:
            lines = [f"Отчёт за период {start_date} — {end_date}:"]
            for eid, full_name, total_hours, overtime_interval, shifts_count in rows:
                total_td = float(total_hours)  # в часах
                total_str = _format_timedelta_to_hours_minutes(total_td)

                ot_td = overtime_interval if overtime_interval else datetime.timedelta(0)
                ot_str = _format_timedelta_to_hours_minutes(ot_td)

                if shifts_count and shifts_count > 0:
                    avg_hours = total_hours / shifts_count
                else:
                    avg_hours = 0.0
                avg_str = _format_timedelta_to_hours_minutes(float(avg_hours))

                lines.append(
                    f"{full_name}: дней: {shifts_count}, общее: {total_str}, "
                    f"ср. в день: {avg_str}, overtime: {ot_str}"
                )
            text = "\n".join(lines)

        await query.edit_message_text(text)
        return ConversationHandler.END

    elif data == "format_excel":
        data_for_df = []
        for eid, full_name, total_hours, overtime_interval, shifts_count in rows:
            total_str = _format_timedelta_to_hours_minutes(float(total_hours))
            ot_td = overtime_interval if overtime_interval else datetime.timedelta(0)
            ot_str = _format_timedelta_to_hours_minutes(ot_td)
            if shifts_count and shifts_count > 0:
                avg_hours = total_hours / shifts_count
            else:
                avg_hours = 0.0
            avg_str = _format_timedelta_to_hours_minutes(float(avg_hours))

            data_for_df.append({
                "ФИО": full_name,
                "Дней": shifts_count,
                "Отработано": total_str,
                "Ср. в день": avg_str,
                "Овертайм": ot_str,
            })

        df = pd.DataFrame(data_for_df, columns=["ФИО", "Дней", "Отработано", "Ср. в день", "Переработка"])

        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Отчёт", index=False)
        output.seek(0)

        bio = BytesIO(output.read())
        bio.name = f"report_{start_date}_{end_date}.xlsx"
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=InputFile(bio),
            caption=f"Отчёт за {start_date} — {end_date}"
        )
        await query.edit_message_text("Вот ваш Excel-файл с отчётом.")
        return ConversationHandler.END

async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Формирование отчёта отменено.")
    return ConversationHandler.END

def reports_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^Отчёты$"), reports_callback),
        ],
        states={
            ASK_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end_date)],
            ASK_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_format)],
            CHOOSE_FORMAT: [CallbackQueryHandler(generate_report, pattern="^(format_text|format_excel|cancel_report)$")],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel_report)],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END,
        },
    )
