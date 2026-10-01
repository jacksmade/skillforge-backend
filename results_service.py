# results_service.py
from db import get_connection
from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_test_results(session_id):
    """Computes stats: score, tier reached, per-tier breakdown, avg time"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT q.difficulty, a.is_correct, a.time_taken_seconds
        FROM attempts a
        JOIN questions q ON a.question_id = q.id
        WHERE a.test_session_id = %s
    """, (session_id,))
    rows = cur.fetchall()

    cur.execute("SELECT current_tier FROM test_sessions WHERE id = %s", (session_id,))
    tier_reached = cur.fetchone()[0]
    cur.close(); conn.close()

    total = len(rows)
    correct = sum(1 for r in rows if r[1])
    avg_time = sum(r[2] for r in rows) / total if total else 0

    # break it down per difficulty tier, since that's what tells us WHERE they're weak
    per_tier = {}
    for difficulty, is_correct, time_taken in rows:
        if difficulty not in per_tier:
            per_tier[difficulty] = {"correct": 0, "total": 0}
        per_tier[difficulty]["total"] += 1
        if is_correct:
            per_tier[difficulty]["correct"] += 1

    return {
        "total_questions": total,
        "total_correct": correct,
        "tier_reached": tier_reached,
        "average_time_seconds": round(avg_time, 1),
        "per_tier_breakdown": per_tier
    }


def generate_feedback(session_id, subtopic_name):
    """ONE Groq call — turns the stats into a readable feedback paragraph"""
    stats = get_test_results(session_id)

    prompt = f"""A student just completed a {subtopic_name} test with this performance:
Total questions: {stats['total_questions']}
Correct: {stats['total_correct']}
Tier reached: {stats['tier_reached']}
Average time per question: {stats['average_time_seconds']} seconds
Breakdown by difficulty: {stats['per_tier_breakdown']}

Write a short, encouraging but honest 3-4 sentence feedback paragraph. Mention what they're strong in, where they need more practice, and one concrete suggestion. Do not just restate the numbers."""

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}]
    )
    feedback_text = resp.choices[0].message.content

    return {**stats, "feedback": feedback_text}


def get_test_review(session_id):
    """Every question from this session: user's answer vs correct answer vs explanation"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT q.question_text, q.options, a.selected_index, q.correct_index, a.is_correct, q.explanation
        FROM attempts a
        JOIN questions q ON a.question_id = q.id
        WHERE a.test_session_id = %s
        ORDER BY a.id
    """, (session_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()

    review = []
    for question_text, options, selected_index, correct_index, is_correct, explanation in rows:
        review.append({
            "question": question_text,
            "options": options,
            "your_answer": options[selected_index],
            "correct_answer": options[correct_index],
            "was_correct": is_correct,
            "explanation": explanation
        })
    return review