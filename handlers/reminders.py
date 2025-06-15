
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
import datetime
from models import create_reminder, get_reminders, delete_reminder, get_employee_by_telegram


(
    LISTING,
    ASK_REMINDER_TEXT,
    ASK_REMINDER_DATETIME,
    CONFIRM_DELETE,
) = range(4)

REMINDER_STATES = {
    "LISTING": LISTING,
    "ASK_TEXT": ASK_REMINDER_TEXT,
    "ASK_DATETIME": ASK_REMINDER_DATETIME,
    "CONFIRM_DELETE": CONFIRM_DELETE,
}

temp_data = {}

async def reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    emp = get_employee_by_telegram(user.id)
    if not emp:
        await update.message.reply_text("Сначала зарегистрируйтесь через /start.")
        return ConversationHandler.END
    employee_id = emp[0]

    rows = get_reminders(employee_id)
    if not rows:
        text = "У вас пока нет сохранённых напоминаний."
        keyboard = [
            [InlineKeyboardButton("Добавить напоминание", callback_data="add_reminder")],
            [InlineKeyboardButton("Назад", callback_data="cancel_reminders")],
        ]
    else:
        lines = []
        buttons = []
        for rid, remind_at, msg in rows:
            dt_str = remind_at.strftime("%Y-%m-%d %H:%M")
            lines.append(f"{rid}. [{dt_str}] {msg}")
            buttons.append([InlineKeyboardButton(f"Удалить {rid}", callback_data=f"del_{rid}")])
        text = "Ваши напоминания:\n" + "\n".join(lines)
        keyboard = [
            [InlineKeyboardButton("Добавить напоминание", callback_data="add_reminder")],
            *buttons,
            [InlineKeyboardButton("Назад", callback_data="cancel_reminders")],
        ]

    kb = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)
    return LISTING

async def handle_list_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_reminder":
        await query.edit_message_text("Введите текст напоминания:")
        return ASK_REMINDER_TEXT

    if data.startswith("del_"):
        rid = int(data.split("_", 1)[1])
        temp_data["del_id"] = rid
        await query.edit_message_text(f"Вы уверены, что хотите удалить напоминание #{rid}?",
                                       reply_markup=InlineKeyboardMarkup([
                                           [InlineKeyboardButton("Да, удалить", callback_data="confirm_delete")],
                                           [InlineKeyboardButton("Отмена", callback_data="cancel_reminders")],
                                       ]))
        return CONFIRM_DELETE

    if data == "cancel_reminders":
        await query.edit_message_text("Отменено. Чтобы снова открыть напоминания, нажмите кнопку «Напоминания».")
        return ConversationHandler.END

    return ConversationHandler.END

async def ask_reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temp_data["message"] = update.message.text
    await update.message.reply_text(
        "Введите дату и время напоминания в формате YYYY-MM-DD HH:MM (24-часовой формат),\n"
        "например: 2025-06-05 14:30"
    )
    return ASK_REMINDER_DATETIME

async def ask_reminder_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    emp = get_employee_by_telegram(user.id)
    if not emp:
        await update.message.reply_text("Сначала зарегистрируйтесь через /start.")
        return ConversationHandler.END

    dt_text = update.message.text.strip()
    try:
        remind_at = datetime.datetime.strptime(dt_text, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text(
            "Неверный формат. Пожалуйста, ещё раз введите дату и время в формате YYYY-MM-DD HH:MM."
        )
        return ASK_REMINDER_DATETIME

    now = datetime.datetime.now()
    if remind_at <= now:
        await update.message.reply_text("Вы указали прошлую дату. Введите дату/время, которое ещё не наступило.")
        return ASK_REMINDER_DATETIME

    message = temp_data.get("message")
    employee_id = emp[0]
    new_row = create_reminder(employee_id, remind_at, message)
    rid, saved_dt, saved_msg = new_row

    context.application.job_queue.run_once(
        callback=send_reminder_job,
        when=(saved_dt - now),
        data={
            "chat_id": update.effective_chat.id,
            "message": saved_msg,
            "reminder_id": rid,
        },
        name=f"reminder_{rid}_{employee_id}",
    )

    await update.message.reply_text(f"Напоминание сохранено на {saved_dt.strftime('%Y-%m-%d %H:%M')}.")

    return await reminders_callback(update, context)

async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rid = temp_data.get("del_id")
    if rid:
        delete_reminder(rid)
        for job in context.application.job_queue.get_jobs_by_name(f"reminder_{rid}_{query.from_user.id}"):
            job.schedule_removal()
        await query.edit_message_text(f"Напоминание #{rid} удалено.")
    else:
        await query.edit_message_text("Что-то пошло не так. Напоминание не найдено.")

    return await reminders_callback(update, context)

async def send_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    message = job_data["message"]
    await context.bot.send_message(chat_id=chat_id, text=f"Напоминание: {message}")

def reminders_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_list_choice, pattern="^(add_reminder|del_\\d+|cancel_reminders)$")],
        states={
            LISTING: [CallbackQueryHandler(handle_list_choice, pattern="^(add_reminder|del_\\d+|cancel_reminders)$")],
            ASK_REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_reminder_text)],
            ASK_REMINDER_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_reminder_datetime)],
            CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete, pattern="^(confirm_delete|cancel_reminders)$")],
        },
        fallbacks=[CallbackQueryHandler(handle_list_choice, pattern="^cancel_reminders$")],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END,
        },
    )