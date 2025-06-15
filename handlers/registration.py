from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database import get_conn, release_conn
from models import INSERT_EMPLOYEE, SELECT_EMPLOYEE_BY_TG
from handlers.work import work_keyboard
from models import get_employee_by_telegram

(
    ASK_LAST_NAME,
    ASK_FIRST_NAME,
    ASK_PATRONYMIC,
    ASK_DEPARTMENT,
    ASK_DIVISION
) = range(5)

def load_departments():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM departments;")
    deps = cur.fetchall()
    dep_map = {name: idx for idx, name in deps}
    cur.execute("SELECT dv.department_id, dv.id, dv.name FROM divisions dv JOIN departments d ON dv.department_id = d.id;")
    div_map = {}
    for dep_id, div_id, div_name in cur.fetchall():
        div_map.setdefault(dep_id, {})[div_name] = div_id
    release_conn(conn)
    return dep_map, div_map

DEPS, DIVS = load_departments()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    conn = get_conn(); cur = conn.cursor()
    cur.execute(SELECT_EMPLOYEE_BY_TG, (tg_id,))
    if cur.fetchone():
        emp = get_employee_by_telegram(tg_id)
        is_admin = (emp and emp[1] == 'admin')
        await update.message.reply_text("Вы уже зарегистрированы. Выберите действие:", reply_markup = work_keyboard(is_admin))

        release_conn(conn)
        return ConversationHandler.END
    release_conn(conn)
    await update.message.reply_text("Добро пожаловать! Пожалуйста, введите Вашу фамилию:")
    return ASK_LAST_NAME

async def last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_name'] = update.message.text
    await update.message.reply_text("Теперь введите Ваше имя:")
    return ASK_FIRST_NAME

async def first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_name'] = update.message.text
    await update.message.reply_text("Введите отчество (или прочерк, если нет):")
    return ASK_PATRONYMIC

async def patronymic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['patronymic'] = update.message.text
    kb = ReplyKeyboardMarkup([[KeyboardButton(name)] for name in DEPS.keys()], resize_keyboard=True)
    await update.message.reply_text("Выберите департамент:", reply_markup=kb)
    return ASK_DEPARTMENT

async def department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dep_name = update.message.text
    dep_id = DEPS.get(dep_name)
    context.user_data['department_id'] = dep_id
    divs = DIVS.get(dep_id, {})
    kb = ReplyKeyboardMarkup([[KeyboardButton(name)] for name in divs.keys()], resize_keyboard=True)
    await update.message.reply_text("Выберите отдел:", reply_markup=kb)
    return ASK_DIVISION

async def division(update: Update, context: ContextTypes.DEFAULT_TYPE):
    div_name = update.message.text
    dep_id = context.user_data['department_id']
    div_id = DIVS[dep_id][div_name]
    data = context.user_data
    conn = get_conn(); cur = conn.cursor()
    cur.execute(
        INSERT_EMPLOYEE,
        (
            update.effective_user.id,
            data['last_name'],
            data['first_name'],
            data['patronymic'],
            dep_id,
            div_id
        )
    )
    conn.commit()
    cur.execute("INSERT INTO online_status (employee_id, is_online) VALUES ((SELECT id FROM employees WHERE telegram_id=%s), FALSE) ON CONFLICT (employee_id) DO NOTHING;", (update.effective_user.id,))
    conn.commit()
    release_conn(conn)
    emp = get_employee_by_telegram(update.effective_user.id)
    is_admin = (emp and emp[1] == 'admin')
    await update.message.reply_text("Регистрация завершена! Выберите действие:", reply_markup = work_keyboard(is_admin))
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Регистрация отменена.")
    return ConversationHandler.END

def registration_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, last_name)],
            ASK_FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, first_name)],
            ASK_PATRONYMIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, patronymic)],
            ASK_DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, department)],
            ASK_DIVISION: [MessageHandler(filters.TEXT & ~filters.COMMAND, division)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
