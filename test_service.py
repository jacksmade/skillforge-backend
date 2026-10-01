# test_service.py
from db import get_connection
from question_service import get_questions_for_test

def start_test(user_id, subject_id, subtopic_id, subtopic_name):
    """Creates a new test session — starting tier depends on past mastery, if any"""
    conn = get_connection()
    cur = conn.cursor()

    # Check if this user has a mastery score for this subtopic already
    cur.execute("""
        SELECT mastery_score FROM user_mastery
        WHERE user_id = %s AND subtopic_id = %s
    """, (user_id, subtopic_id))
    row = cur.fetchone()

    # Cold start = Easy. Returning user with 75%+ mastery = start at Medium (never higher, per our rule)
    if row and row[0] >= 75:
        starting_tier = "medium"
    else:
        starting_tier = "easy"

    cur.execute("""
        INSERT INTO test_sessions (user_id, subject_id, subtopic_id, current_tier)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (user_id, subject_id, subtopic_id, starting_tier))
    session_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()

    questions = get_questions_for_test(user_id, subtopic_id, subtopic_name, starting_tier, count=5)
    return {"session_id": session_id, "tier": starting_tier, "questions": questions}


def record_answer(session_id, question_id, selected_index, time_taken_seconds):
    """Saves one answer, checks if it was correct, returns True/False"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT correct_index FROM questions WHERE id = %s", (question_id,))
    correct_index = cur.fetchone()[0]
    is_correct = (selected_index == correct_index)

    cur.execute("""
        INSERT INTO attempts (test_session_id, question_id, selected_index, is_correct, time_taken_seconds)
        VALUES (%s, %s, %s, %s, %s)
    """, (session_id, question_id, selected_index, is_correct, time_taken_seconds))
    conn.commit()
    cur.close(); conn.close()
    return is_correct


TIER_ORDER = ["easy", "medium", "hard"]

def get_tier_results(session_id, tier):
    """Count how many correct/incorrect in the CURRENT tier's 5 questions"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT a.is_correct FROM attempts a
        JOIN questions q ON a.question_id = q.id
        WHERE a.test_session_id = %s AND q.difficulty = %s
    """, (session_id, tier))
    results = [row[0] for row in cur.fetchall()]
    cur.close(); conn.close()
    return results
def update_mastery(user_id, subtopic_id, session_id):
    """Called when a test finishes — updates this user's mastery score for this subtopic"""
    conn = get_connection()
    cur = conn.cursor()

    # Get this session's performance
    cur.execute("""
        SELECT COUNT(*), SUM(CASE WHEN is_correct THEN 1 ELSE 0 END)
        FROM attempts WHERE test_session_id = %s
    """, (session_id,))
    total, correct = cur.fetchone()
    new_score = round((correct / total) * 100) if total else 0

    # Check if a mastery row already exists for this user+subtopic
    cur.execute("""
        SELECT mastery_score FROM user_mastery
        WHERE user_id = %s AND subtopic_id = %s
    """, (user_id, subtopic_id))
    existing = cur.fetchone()

    if existing:
        # Recency-weighted: blend old score with new (70% new, 30% old — recent performance matters more)
        old_score = existing[0]
        blended_score = round((new_score * 0.7) + (old_score * 0.3))
        cur.execute("""
            UPDATE user_mastery
            SET mastery_score = %s, last_attempted_at = now()
            WHERE user_id = %s AND subtopic_id = %s
        """, (blended_score, user_id, subtopic_id))
    else:
        cur.execute("""
            INSERT INTO user_mastery (user_id, subtopic_id, mastery_score, last_attempted_at)
            VALUES (%s, %s, %s, now())
        """, (user_id, subtopic_id, new_score))

    conn.commit()
    cur.close(); conn.close()

def get_total_attempts_count(session_id):
    """Count ALL questions answered so far in this entire test session, across all tiers"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM attempts WHERE test_session_id = %s", (session_id,))
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    return count

def decide_next_step(session_id, user_id, subtopic_id, subtopic_name):
    """THE CORE ADAPTIVE RULE — call this after every 5 questions are answered"""
     # SAFETY CAP — force the test to end after 20 total questions, no matter what
    total_so_far = get_total_attempts_count(session_id)
    if total_so_far >= 20:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT current_tier FROM test_sessions WHERE id = %s", (session_id,))
        current_tier = cur.fetchone()[0]
        cur.close(); conn.close()
        update_mastery(user_id, subtopic_id, session_id)
        return {"action": "finished", "tier_reached": current_tier, "reason": "max_questions_reached"}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_tier, tier_repeat_count FROM test_sessions WHERE id = %s", (session_id,))
    current_tier, repeat_count = cur.fetchone()

    results = get_tier_results(session_id, current_tier)
    correct_count = sum(results)

    if correct_count >= 4:
        current_index = TIER_ORDER.index(current_tier)
        if current_index == len(TIER_ORDER) - 1:
            action = "finished"
        else:
            next_tier = TIER_ORDER[current_index + 1]
            action = "advance"
            cur.execute("UPDATE test_sessions SET current_tier = %s, tier_repeat_count = 0 WHERE id = %s",
                        (next_tier, session_id))
            current_tier = next_tier

    elif correct_count <= 1:
        current_index = TIER_ORDER.index(current_tier)
        if current_index == 0:
            action = "finished"
        else:
            next_tier = TIER_ORDER[current_index - 1]
            action = "advance"
            cur.execute("UPDATE test_sessions SET current_tier = %s, tier_repeat_count = 0 WHERE id = %s",
                        (next_tier, session_id))
            current_tier = next_tier

    else:
        if repeat_count >= 1:
            action = "advance"
            current_index = TIER_ORDER.index(current_tier)
            next_tier = TIER_ORDER[min(current_index + 1, len(TIER_ORDER) - 1)]
            cur.execute("UPDATE test_sessions SET current_tier = %s, tier_repeat_count = 0 WHERE id = %s",
                        (next_tier, session_id))
            current_tier = next_tier
        else:
            action = "repeat"
            cur.execute("UPDATE test_sessions SET tier_repeat_count = 1 WHERE id = %s", (session_id,))

    conn.commit()
    cur.close(); conn.close()

    if action == "finished":
        update_mastery(user_id, subtopic_id, session_id)
        return {"action": "finished", "tier_reached": current_tier}

    questions = get_questions_for_test(user_id, subtopic_id, subtopic_name, current_tier, count=5)
    return {"action": action, "tier": current_tier, "questions": questions}
def get_mastery_summary(user_id, subtopic_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT mastery_score, last_attempted_at FROM user_mastery
        WHERE user_id = %s AND subtopic_id = %s
    """, (user_id, subtopic_id))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return {"has_history": False}
    return {"has_history": True, "mastery_score": row[0], "last_attempted_at": str(row[1])}
    