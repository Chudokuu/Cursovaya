import datetime
from typing import List, Optional, Tuple
from database import get_conn, release_conn


INSERT_EMPLOYEE = """
INSERT INTO employees (telegram_id, last_name, first_name, patronymic, department_id, division_id)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (telegram_id) DO NOTHING
RETURNING id;
"""
SELECT_EMPLOYEE_BY_TG = "SELECT id, role, department_id, division_id FROM employees WHERE telegram_id = %s;"

INSERT_ONLINE_STATUS = """
INSERT INTO online_status (employee_id, is_online)
VALUES (%s, %s)
ON CONFLICT (employee_id) DO NOTHING;
"""
UPDATE_ONLINE_STATUS = """
UPDATE online_status
SET is_online = %s, updated_at = NOW()
WHERE employee_id = %s;
"""

INSERT_WORK_SESSION = """
INSERT INTO work_sessions (employee_id, started_at)
VALUES (%s, %s);
"""
UPDATE_WORK_SESSION_END = """
UPDATE work_sessions
SET ended_at = %s, duration = %s - started_at
WHERE employee_id = %s AND ended_at IS NULL;
"""
SELECT_ACTIVE_SESSION = """
SELECT id FROM work_sessions
WHERE employee_id = %s AND ended_at IS NULL
ORDER BY started_at DESC LIMIT 1;
"""

INSERT_BREAK = """
INSERT INTO breaks (session_id, started_at)
VALUES (%s, %s);
"""
UPDATE_BREAK_END = """
UPDATE breaks
SET ended_at = %s, duration = %s - started_at
WHERE id = %s;
"""

SELECT_COLLEAGUES = """
SELECT e.last_name, e.first_name
FROM employees e
JOIN online_status o ON e.id = o.employee_id
WHERE o.is_online = TRUE
  AND e.department_id = %s
  AND e.division_id = %s;
"""

AVG_WORK_TIME = """
SELECT AVG(EXTRACT(EPOCH FROM duration)) AS avg_seconds
FROM work_sessions
WHERE employee_id = %s
  AND started_at >= NOW() - INTERVAL %s
  AND duration IS NOT NULL;
"""

SELECT_EMPLOYEES_BY_DEP_DIV = """
SELECT id, last_name || ' ' || first_name AS full_name
FROM employees
WHERE department_id = %s AND division_id = %s;
"""
UPDATE_EMPLOYEE_ROLE = """
UPDATE employees SET role = %s, updated_at = NOW() WHERE id = %s;
"""

UPDATE_EMPLOYEE_OVERTIME = """
UPDATE employees
SET overtime = overtime + %s
WHERE id = %s;
"""

SELECT_EMPLOYEE_OVERTIME = """
SELECT overtime FROM employees WHERE id = %s;
"""

INSERT_REMINDER = """
INSERT INTO reminders (employee_id, remind_at, message)
VALUES (%s, %s, %s)
RETURNING id, remind_at, message;
"""

SELECT_REMINDERS_BY_EMP = """
SELECT id, remind_at, message
FROM reminders
WHERE employee_id = %s
ORDER BY remind_at ASC;
"""

DELETE_REMINDER_BY_ID = """
DELETE FROM reminders WHERE id = %s;
"""


def get_employee_by_telegram(telegram_id: int) -> Optional[Tuple[int, str, int, int]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_EMPLOYEE_BY_TG, (telegram_id,))
    row = cur.fetchone()
    release_conn(conn)
    return row


def create_employee(telegram_id: int, last_name: str, first_name: str, patronymic: str,
                    department_id: int, division_id: int) -> Optional[int]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(INSERT_EMPLOYEE, (telegram_id, last_name, first_name, patronymic, department_id, division_id))
    res = cur.fetchone()
    conn.commit()
    if res:
        emp_id = res[0]
    else:
        cur.execute(SELECT_EMPLOYEE_BY_TG, (telegram_id,))
        emp_id = cur.fetchone()[0]
    cur.execute(INSERT_ONLINE_STATUS, (emp_id, False))
    conn.commit()
    release_conn(conn)
    return emp_id


def set_online_status(employee_id: int, is_online: bool):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(UPDATE_ONLINE_STATUS, (is_online, employee_id))
    conn.commit()
    release_conn(conn)


def start_work_session(employee_id: int) -> None:
    now = datetime.datetime.now()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(INSERT_WORK_SESSION, (employee_id, now))
    cur.execute(UPDATE_ONLINE_STATUS, (True, employee_id))
    conn.commit()
    release_conn(conn)


def end_work_session(employee_id: int) -> None:
    now = datetime.datetime.now()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(UPDATE_WORK_SESSION_END, (now, now, employee_id))
    cur.execute(UPDATE_ONLINE_STATUS, (False, employee_id))
    conn.commit()
    release_conn(conn)


def start_break(employee_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_ACTIVE_SESSION, (employee_id,))
    session_id = cur.fetchone()[0]
    now = datetime.datetime.now()
    cur.execute(INSERT_BREAK, (session_id, now))
    cur.execute(UPDATE_ONLINE_STATUS, (False, employee_id))
    conn.commit()
    release_conn(conn)


def end_break(employee_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_ACTIVE_SESSION, (employee_id,))
    session_id = cur.fetchone()[0]
    cur.execute("""
        SELECT id FROM breaks WHERE session_id = %s AND ended_at IS NULL
        ORDER BY started_at DESC LIMIT 1;
    """, (session_id,))
    break_id = cur.fetchone()[0]
    now = datetime.datetime.now()
    cur.execute(UPDATE_BREAK_END, (now, now, break_id))
    cur.execute(UPDATE_ONLINE_STATUS, (True, employee_id))
    conn.commit()
    release_conn(conn)


def get_colleagues(department_id: int, division_id: int) -> List[Tuple[str, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_COLLEAGUES, (department_id, division_id))
    rows = cur.fetchall()
    release_conn(conn)
    return rows


def get_average_work_time(employee_id: int, interval: str) -> float:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(AVG_WORK_TIME, (employee_id, interval))
    res = cur.fetchone()[0] or 0.0
    release_conn(conn)
    return res


def list_employees(department_id: int, division_id: int) -> List[Tuple[int, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_EMPLOYEES_BY_DEP_DIV, (department_id, division_id))
    rows = cur.fetchall()
    release_conn(conn)
    return rows


def set_employee_role(employee_id: int, role: str) -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(UPDATE_EMPLOYEE_ROLE, (role, employee_id))
    conn.commit()
    release_conn(conn)

def create_reminder(employee_id: int, remind_at: datetime.datetime, message: str) -> Tuple[int, datetime.datetime, str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(INSERT_REMINDER, (employee_id, remind_at, message))
    row = cur.fetchone()
    conn.commit()
    release_conn(conn)
    return row

def get_reminders(employee_id: int) -> List[Tuple[int, datetime.datetime, str]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_REMINDERS_BY_EMP, (employee_id,))
    rows = cur.fetchall()
    release_conn(conn)
    return rows

def delete_reminder(reminder_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(DELETE_REMINDER_BY_ID, (reminder_id,))
    conn.commit()
    release_conn(conn)

def get_employee_overtime(employee_id: int) -> datetime.timedelta:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(SELECT_EMPLOYEE_OVERTIME, (employee_id,))
    row = cur.fetchone()
    release_conn(conn)
    return row[0] if row and row[0] is not None else datetime.timedelta(0)