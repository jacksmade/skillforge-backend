# main.py
from fastapi import FastAPI
from question_service import get_questions_for_test
from results_service import generate_feedback, get_test_review
from subjects_service import get_all_subjects, get_subtopics_for_subject
from test_service import start_test, record_answer, decide_next_step
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends
from auth_service import get_current_user
from test_service import get_mastery_summary

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allows any frontend to call this — fine for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/user/mastery")
def api_get_mastery(subtopic_id: int,user_id: str = Depends(get_current_user)):
    return get_mastery_summary(user_id, subtopic_id)

@app.get("/test/questions")
def get_test_questions(subtopic_id: int, subtopic_name: str, difficulty: str,user_id: str = Depends(get_current_user)):
    questions = get_questions_for_test(user_id, subtopic_id, subtopic_name, difficulty, count=5)
    return {"questions": questions}


@app.post("/test/start")
def api_start_test(subject_id: int, subtopic_id: int, subtopic_name: str, user_id: str = Depends(get_current_user)):
    return start_test(user_id, subject_id, subtopic_id, subtopic_name)

@app.post("/test/{session_id}/answer")
def api_record_answer(session_id: int, question_id: int, selected_index: int, time_taken_seconds: int, user_id: str = Depends(get_current_user)):
    is_correct = record_answer(session_id, question_id, selected_index, time_taken_seconds)
    return {"is_correct": is_correct}

@app.post("/test/{session_id}/next")
def api_next_step(session_id: int, subtopic_id: int, subtopic_name: str, user_id: str = Depends(get_current_user)):
    return decide_next_step(session_id, user_id, subtopic_id, subtopic_name)

@app.get("/test/{session_id}/results")
def api_get_results(session_id: int, subtopic_name: str):
    return generate_feedback(session_id, subtopic_name)

@app.get("/test/{session_id}/review")
def api_get_review(session_id: int):
    return get_test_review(session_id)

@app.get("/subjects")
def api_get_subjects():
    return get_all_subjects()

@app.get("/subjects/{subject_id}/subtopics")
def api_get_subtopics(subject_id: int):
    return get_subtopics_for_subject(subject_id)