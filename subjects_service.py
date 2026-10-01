# subjects_service.py
from db import get_connection

def get_all_subjects():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM subjects ORDER BY name")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]

def get_subtopics_for_subject(subject_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM subtopics WHERE subject_id = %s ORDER BY name", (subject_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{"id": r[0], "name": r[1]} for r in rows]