from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from database import get_conn, release_conn
from handlers.registration import DEPS, DIVS
from models import set_employee_role, get_employee_by_telegram

(
    CHOOSING_DEP,
    CHOOSING_DIV,
    CHOOSING_EMP,
    CONFIRM_PROMOTE,
    CONFIRM_DELETE
) = range(5)


from handlers.registration import DEPS, DIVS

promote_data = {}
action_type = None

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Дать админ", callback_data="admin_promote")],
        [InlineKeyboardButton("Удалить", callback_data="admin_delete")],
        [InlineKeyboardButton("Отчёты", callback_data="admin_reports")],
    ])
    await update.callback_query.edit_message_text("Выберите действие администратора:", reply_markup=kb)

async def start_promote_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global action_type
    action_type = 'promote'
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=name)] for name in DEPS.keys()])
    prompt = "Выберите департамент:"
    if update.callback_query:
        await update.callback_query.edit_message_text(prompt, reply_markup=kb)
    else:
        await update.message.reply_text(prompt, reply_markup=kb)
    return CHOOSING_DEP

async def start_delete_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global action_type
    action_type = 'delete'
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=name)] for name in DEPS.keys()])
    prompt = "Выберите департамент:"
    if update.callback_query:
        await update.callback_query.edit_message_text(prompt, reply_markup=kb)
    else:
        await update.message.reply_text(prompt, reply_markup=kb)
    return CHOOSING_DEP

async def choose_dep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dep = update.callback_query.data
    promote_data['dep_id'] = DEPS[dep]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(name, callback_data=name)] for name in DIVS[promote_data['dep_id']].keys()])
    await update.callback_query.edit_message_text("Выберите отдел:", reply_markup=kb)
    return CHOOSING_DIV

async def choose_div(update: Update, context: ContextTypes.DEFAULT_TYPE):
    div = update.callback_query.data
    promote_data['div_id'] = DIVS[promote_data['dep_id']][div]
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        SELECT id, last_name || ' ' || first_name FROM employees
        WHERE department_id=%s AND division_id=%s;
    """, (promote_data['dep_id'], promote_data['div_id']))
    rows = cur.fetchall()
    release_conn(conn)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(txt, callback_data=str(emp_id))] for emp_id, txt in rows])
    await update.callback_query.edit_message_text("Выберите сотрудника:", reply_markup=kb)
    return CHOOSING_EMP

async def choose_emp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emp_id = int(update.callback_query.data)
    promote_data['emp_id'] = emp_id
    text = "Подтвердите действие:"
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("Да", callback_data="yes"),
        InlineKeyboardButton("Отмена", callback_data="no")
    ]])
    await update.callback_query.edit_message_text(text, reply_markup=kb)
    return CONFIRM_PROMOTE

async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.callback_query.data
    if ans != 'yes':
        await update.callback_query.edit_message_text("Операция отменена.")
        return ConversationHandler.END

    conn = get_conn(); cur = conn.cursor()
    if action_type == 'promote':
        cur.execute("UPDATE employees SET role='admin' WHERE id=%s;", (promote_data['emp_id'],))
    else:
        cur.execute("UPDATE employees SET role='worker' WHERE id=%s;", (promote_data['emp_id'],))
    conn.commit(); release_conn(conn)

    msg = "Права изменены." if action_type=='promote' else "Админ снят."
    await update.callback_query.edit_message_text(msg)
    return ConversationHandler.END

def admin_handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_promote_cb, pattern="^admin_promote$"),
            CallbackQueryHandler(start_delete_cb, pattern="^admin_delete$"),
            MessageHandler(filters.Regex("^Дать админ$"), start_promote_cb),
            MessageHandler(filters.Regex("^Удалить$"), start_delete_cb),
        ],
        states={
            CHOOSING_DEP: [CallbackQueryHandler(choose_dep)],
            CHOOSING_DIV: [CallbackQueryHandler(choose_div)],
            CHOOSING_EMP: [CallbackQueryHandler(choose_emp)],
            CONFIRM_PROMOTE: [CallbackQueryHandler(confirm_cb, pattern="^(yes|no)$")],
        },
        fallbacks=[]
    )
