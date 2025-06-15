from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from config import TELEGRAM_TOKEN
from handlers.registration import registration_handler
from handlers.work import menu, start_work_cb, end_work_cb, start_break_cb, end_break_cb
from handlers.colleagues import colleagues_cb
from handlers.stats import stats_cb
from handlers.admin import admin_menu, admin_handler
from handlers.reminders import reminders_handler, REMINDER_STATES, reminders_callback  # новый
from handlers.reports import reports_handler, REPORT_STATES  # новый

async def unknown(update, context):
    await update.message.reply_text("Извините, я не понимаю команду. Используйте /start, чтобы зарегистрироваться, или кнопку меню.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(registration_handler())
    app.add_handler(CommandHandler("menu", menu))

    from telegram.ext import MessageHandler, filters as ext_filters
    app.add_handler(MessageHandler(ext_filters.Regex("^Начал$"), start_work_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Закончил$"), end_work_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Отошел$"), start_break_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Вернулся$"), end_break_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Коллеги$"), colleagues_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Статистика$"), stats_cb))
    app.add_handler(MessageHandler(ext_filters.Regex("^Напоминания$"), reminders_callback))
    app.add_handler(reminders_handler())

    app.add_handler(CallbackQueryHandler(admin_menu, pattern="^menu_admin$"))
    app.add_handler(admin_handler())
    app.add_handler(reports_handler())

    from telegram.ext import MessageHandler, filters as ext_filters
    app.add_handler(MessageHandler(ext_filters.COMMAND, unknown))

    app.run_polling()

if __name__ == "__main__":
    main()


#pip install -r requirements.txt
#python bot.py


