# question_service.py
import json, time, os
from db import get_connection
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_unseen_questions(user_id, subtopic_id, difficulty, needed_count):
    """Check DB first — questions this user hasn't seen yet"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, question_text, options, correct_index, explanation
        FROM questions
        WHERE subtopic_id = %s AND difficulty = %s
        AND id NOT IN (
            SELECT a.question_id FROM attempts a
            JOIN test_sessions ts ON a.test_session_id = ts.id
            WHERE ts.user_id = %s
        )
        LIMIT %s
    """, (subtopic_id, difficulty, user_id, needed_count))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def generate_question(subtopic_name, difficulty):
    """Generate ONE new question via Groq, only called when DB is short"""
    prompt = f"""Generate one {difficulty}-difficulty multiple choice question about {subtopic_name}.

Difficulty rubric:
- easy = definition/recall
- medium = apply the concept to an example
- hard = combines multiple concepts or a common gotcha

Return ONLY valid JSON, no other text:
{{"question": "...", "options": ["a","b","c","d"], "correct_index": 0, "explanation": "..."}}"""

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(resp.choices[0].message.content)

def self_check(question_data):
    """Validate — ask Groq to independently re-solve, no hints given"""
    check_prompt = f"""Question: {question_data['question']}
Options: {question_data['options']}

Which option is correct? Return ONLY the index number (0-3), nothing else."""

    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": check_prompt}]
    )
    try:
        model_answer = int(resp.choices[0].message.content.strip())
        return model_answer == question_data["correct_index"]
    except ValueError:
        return False  # couldn't parse cleanly, treat as failed

def save_question(subtopic_id, difficulty, question_data):
    """Save validated question so it's reused next time, not regenerated"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO questions (subtopic_id, difficulty, question_text, options, correct_index, explanation, source)
        VALUES (%s, %s, %s, %s, %s, %s, 'groq_generated')
        RETURNING id
    """, (
        subtopic_id, difficulty, question_data["question"],
        json.dumps(question_data["options"]), question_data["correct_index"],
        question_data["explanation"]
    ))
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return new_id

def get_questions_for_test(user_id, subtopic_id, subtopic_name, difficulty, count=5):
    """THE MAIN FUNCTION — hybrid logic lives here"""
    existing = get_unseen_questions(user_id, subtopic_id, difficulty, count)
    shortfall = count - len(existing)

    if shortfall <= 0:
        return existing  # DB had enough — no Groq call needed at all

    generated = []
    attempts = 0
    while len(generated) < shortfall and attempts < shortfall * 3:
        attempts += 1
        q = generate_question(subtopic_name, difficulty)
        if self_check(q):
            new_id = save_question(subtopic_id, difficulty, q)
            generated.append((new_id, q["question"], q["options"], q["correct_index"], q["explanation"]))
        time.sleep(0.3)

    return existing + generated