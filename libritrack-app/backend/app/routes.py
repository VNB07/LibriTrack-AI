"""All API endpoints. Every endpoint except login requires a staff token."""
import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ml.recogniser import (
    embedding_from_file,
    extract_and_save_book_features,
    identify_book_only,
    identify_face_only,
)
from app.db import (
    BOOK_DIR,
    PHOTO_DIR,
    SNAPSHOT_DIR,
    execute,
    query,
)
from app.security import check_password, current_staff, make_token

router = APIRouter()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Auth ----------

class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn):
    staff = query("SELECT * FROM staff WHERE email=?", (body.email,), one=True)
    if not staff or not check_password(body.password, staff["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(staff["id"], staff["role"]), "name": staff["name"], "role": staff["role"]}


# ---------- Students & Attendance ----------

class StudentIn(BaseModel):
    code: str
    name: str
    email: Optional[str] = None
    consent: bool


@router.get("/students")
def list_students(_=Depends(current_staff)):
    return query("""
        SELECT s.id, s.student_code, s.name, s.email, s.consent_at,
               (SELECT COUNT(*) FROM photos p WHERE p.student_id = s.id) AS photos,
               (SELECT kind FROM events e WHERE e.student_id = s.id ORDER BY e.id DESC LIMIT 1) AS last_event,
               (SELECT at FROM events e WHERE e.student_id = s.id ORDER BY e.id DESC LIMIT 1) AS last_event_at
        FROM students s ORDER BY s.name
    """)


@router.get("/students/inside")
def list_students_inside(_=Depends(current_staff)):
    """Returns currently present students inside the library."""
    return query("""
        SELECT s.id, s.student_code, s.name, s.email, e.at AS entered_at, e.source
        FROM events e
        JOIN students s ON s.id = e.student_id
        WHERE e.id IN (SELECT MAX(id) FROM events GROUP BY student_id)
          AND e.kind = 'entry'
        ORDER BY e.at DESC
    """)


@router.post("/students")
def add_student(body: StudentIn, _=Depends(current_staff)):
    try:
        student_id = execute(
            "INSERT INTO students(student_code,name,email,consent_at) VALUES(?,?,?,?)",
            (body.code.strip(), body.name.strip(), (body.email or "").strip() or None, now() if body.consent else None))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A student with this code already exists")
    return {"id": student_id}


@router.post("/students/{student_id}/photos")
async def upload_photo(student_id: int, file: UploadFile = File(...), staff=Depends(current_staff)):
    student = query("SELECT * FROM students WHERE id=?", (student_id,), one=True)
    if not student:
        raise HTTPException(404, "Student not found")
    if not student["consent_at"]:
        raise HTTPException(403, "This student has not consented to face recognition")

    folder = os.path.join(PHOTO_DIR, str(student_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, uuid.uuid4().hex + ".jpg")
    with open(path, "wb") as f:
        f.write(await file.read())

    embedding = embedding_from_file(path)
    if embedding is None:
        os.remove(path)
        raise HTTPException(422, "The photo must show exactly one clearly visible face")

    execute("INSERT INTO photos(student_id,uploaded_by,path,embedding,created_at) VALUES(?,?,?,?,?)",
            (student_id, staff["id"], path, json.dumps(embedding), now()))
    return {"ok": True}


@router.get("/me/photos")
def my_photos(staff=Depends(current_staff)):
    return query("""
        SELECT p.id, p.created_at, s.name AS student, s.student_code
        FROM photos p JOIN students s ON s.id = p.student_id
        WHERE p.uploaded_by = ? ORDER BY p.id DESC
    """, (staff["id"],))


@router.delete("/students/{student_id}/photos")
def withdraw_consent(student_id: int, _=Depends(current_staff)):
    for photo in query("SELECT path FROM photos WHERE student_id=?", (student_id,)):
        if os.path.exists(photo["path"]):
            os.remove(photo["path"])
    execute("DELETE FROM photos WHERE student_id=?", (student_id,))
    execute("UPDATE students SET consent_at=NULL WHERE id=?", (student_id,))
    return {"ok": True, "message": "Consent withdrawn and face data deleted"}


# ---------- Books & Loans ----------

@router.get("/books")
def list_books(_=Depends(current_staff)):
    return query("""
        SELECT b.*, b.copies - (SELECT COUNT(*) FROM loans l
             WHERE l.barcode = b.barcode AND l.returned_at IS NULL) AS available
        FROM books b ORDER BY b.title
    """)


@router.post("/books")
async def add_book(
    barcode: str = Form(...),
    title: str = Form(...),
    author: Optional[str] = Form(""),
    copies: Optional[str] = Form("1"),
    cover: Optional[UploadFile] = File(None),
    _=Depends(current_staff)
):
    try:
        num_copies = int(copies) if copies else 1
    except ValueError:
        num_copies = 1

    cover_path = None
    features_path = None

    if cover and cover.filename:
        content = await cover.read()
        if len(content) > 0:
            ext = os.path.splitext(cover.filename)[1] or ".jpg"
            filename = f"{uuid.uuid4().hex}{ext}"
            cover_path = os.path.join(BOOK_DIR, filename)
            features_path = os.path.join(BOOK_DIR, f"{uuid.uuid4().hex}.npz")

            with open(cover_path, "wb") as f:
                f.write(content)

            success = extract_and_save_book_features(cover_path, features_path)
            if not success:
                if os.path.exists(cover_path):
                    os.remove(cover_path)
                raise HTTPException(422, "Unable to extract distinct visual features. Please use a clearer, well-lit image of the book cover.")

    try:
        book_id = execute(
            "INSERT INTO books(barcode,title,author,copies,cover_path,features_path) VALUES(?,?,?,?,?,?)",
            (barcode.strip(), title.strip(), (author or "").strip(), num_copies, cover_path, features_path)
        )
    except sqlite3.IntegrityError:
        if cover_path and os.path.exists(cover_path):
            os.remove(cover_path)
        if features_path and os.path.exists(features_path):
            os.remove(features_path)
        raise HTTPException(409, f"A book with barcode '{barcode}' already exists.")
    return {"id": book_id}


class CheckoutIn(BaseModel):
    barcode: str
    student_id: int
    days: int = 14
    snapshot_path: Optional[str] = None


@router.post("/loans/checkout")
def checkout(body: CheckoutIn, _=Depends(current_staff)):
    book = query("SELECT * FROM books WHERE barcode=?", (body.barcode,), one=True)
    if not book:
        raise HTTPException(404, "Unknown book barcode")
    if not query("SELECT id FROM students WHERE id=?", (body.student_id,), one=True):
        raise HTTPException(404, "Student not found")
    open_count = query("SELECT COUNT(*) AS n FROM loans WHERE barcode=? AND returned_at IS NULL",
                       (body.barcode,), one=True)["n"]
    if open_count >= book["copies"]:
        raise HTTPException(409, "No copies available")
    due = (datetime.now(timezone.utc) + timedelta(days=body.days)).isoformat(timespec="seconds")
    execute("INSERT INTO loans(barcode,student_id,borrowed_at,due_at,snapshot_path) VALUES(?,?,?,?,?)",
            (body.barcode, body.student_id, now(), due, body.snapshot_path))
    return {"ok": True, "due_at": due}


class ReturnIn(BaseModel):
    barcode: str


@router.post("/loans/return")
def return_book(body: ReturnIn, _=Depends(current_staff)):
    loan = query("SELECT id FROM loans WHERE barcode=? AND returned_at IS NULL ORDER BY borrowed_at LIMIT 1",
                 (body.barcode,), one=True)
    if not loan:
        raise HTTPException(404, "No open loan for this barcode")
    execute("UPDATE loans SET returned_at=? WHERE id=?", (now(), loan["id"]))
    return {"ok": True}


@router.get("/loans")
def list_loans(_=Depends(current_staff)):
    today = now()
    return query("""
        SELECT l.id, l.barcode, b.title, s.name AS student, s.student_code, l.borrowed_at, l.due_at, l.snapshot_path,
               CASE WHEN l.due_at < ? THEN 1 ELSE 0 END AS overdue
        FROM loans l 
        JOIN books b ON b.barcode = l.barcode 
        JOIN students s ON s.id = l.student_id
        WHERE l.returned_at IS NULL 
        ORDER BY l.borrowed_at DESC
    """, (today,))


# ---------- Unattended Books & Snapshots ----------

@router.get("/unattended-books")
def list_unattended_books(_=Depends(current_staff)):
    return query("""
        SELECT ub.id, ub.barcode, ub.detected_at, ub.snapshot_path, b.title
        FROM unattended_books ub
        LEFT JOIN books b ON b.barcode = ub.barcode
        WHERE ub.status = 'unreviewed'
        ORDER BY ub.detected_at DESC LIMIT 50
    """)


@router.post("/unattended-books/{entry_id}/dismiss")
def dismiss_unattended_book(entry_id: int, _=Depends(current_staff)):
    execute("UPDATE unattended_books SET status = 'dismissed' WHERE id = ?", (entry_id,))
    return {"ok": True}


@router.get("/snapshots/{filename}")
def get_snapshot(filename: str, _=Depends(current_staff)):
    safe_name = os.path.basename(filename)
    path = os.path.join(SNAPSHOT_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(path)


# ---------- Vision Helpers ----------

def inside_ids() -> set:
    rows = query("""
        SELECT student_id FROM events
        WHERE id IN (SELECT MAX(id) FROM events GROUP BY student_id) AND kind = 'entry'
    """)
    return {r["student_id"] for r in rows}


def face_gallery() -> list:
    rows = query("""
        SELECT p.student_id, p.embedding FROM photos p
        JOIN students s ON s.id = p.student_id
        WHERE s.consent_at IS NOT NULL AND s.active = 1
    """)
    grouped = {}
    for r in rows:
        grouped.setdefault(r["student_id"], []).append(json.loads(r["embedding"]))
    return list(grouped.items())


def book_gallery() -> list:
    rows = query("SELECT barcode, features_path FROM books WHERE features_path IS NOT NULL")
    gallery = []
    for r in rows:
        if r["features_path"] and os.path.exists(r["features_path"]):
            data = np.load(r["features_path"])
            gallery.append({
                "barcode": r["barcode"],
                "pts": data["pts"],
                "des": data["des"],
                "shape": tuple(data["shape"])
            })
    return gallery


# ---------- Attendance Mode Endpoint ----------

@router.post("/recognise")
async def recognise(file: UploadFile = File(...), _=Depends(current_staff)):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        frame_content = await file.read()
        tmp.write(frame_content)
        frame_path = tmp.name

    try:
        result = identify_face_only(frame_path, face_gallery())
    finally:
        os.remove(frame_path)

    already_inside = inside_ids()
    faces_out = []
    for face in result["faces"]:
        student_id = face["student_id"]
        name = "Unknown"
        if student_id is not None:
            row = query("SELECT name FROM students WHERE id=?", (student_id,), one=True)
            name = row["name"] if row else "Unknown"
            if student_id not in already_inside:
                execute("INSERT INTO events(student_id,kind,source,at) VALUES(?,?,?,?)",
                        (student_id, "entry", "face", now()))
                already_inside.add(student_id)
        faces_out.append({"student_id": student_id, "name": name, "box": face["box"]})

    return {"width": result["width"], "height": result["height"], "faces": faces_out, "books": []}


# ---------- Borrow Mode Endpoints ----------

@router.post("/borrow/verify-student")
async def borrow_verify_student(file: UploadFile = File(...), _=Depends(current_staff)):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        frame_content = await file.read()
        tmp.write(frame_content)
        frame_path = tmp.name

    try:
        result = identify_face_only(frame_path, face_gallery())
    finally:
        os.remove(frame_path)

    enrolled = [f for f in result["faces"] if f["student_id"] is not None]
    if not enrolled:
        return {"verified": False, "faces": result["faces"], "width": result["width"], "height": result["height"]}

    primary_student = enrolled[0]
    row = query("SELECT id, name, student_code FROM students WHERE id=?", (primary_student["student_id"],), one=True)

    return {
        "verified": True,
        "student": dict(row) if row else None,
        "faces": [primary_student],
        "width": result["width"],
        "height": result["height"]
    }


@router.post("/borrow/scan-book")
async def borrow_scan_book(
    student_id: int = Form(...),
    file: UploadFile = File(...),
    _=Depends(current_staff)
):
    student = query("SELECT id, name FROM students WHERE id=?", (student_id,), one=True)
    if not student:
        raise HTTPException(404, "Student not found")

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        frame_content = await file.read()
        tmp.write(frame_content)
        frame_path = tmp.name

    try:
        result = identify_book_only(frame_path, book_gallery())
    finally:
        os.remove(frame_path)

    books_matched = result["books"]
    if not books_matched:
        return {"matched": False, "books": [], "width": result["width"], "height": result["height"]}

    book_match = max(books_matched, key=lambda b: b["matches"])
    barcode = book_match["barcode"]
    b_info = query("SELECT title, copies FROM books WHERE barcode=?", (barcode,), one=True)
    title = b_info["title"] if b_info else barcode

    snapshot_name = f"checkout_{uuid.uuid4().hex}.jpg"
    snap_path = os.path.join(SNAPSHOT_DIR, snapshot_name)
    with open(snap_path, "wb") as f:
        f.write(frame_content)

    existing = query("SELECT id FROM loans WHERE barcode=? AND returned_at IS NULL", (barcode,), one=True)
    due = None
    if not existing:
        due = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(timespec="seconds")
        execute("INSERT INTO loans(barcode,student_id,borrowed_at,due_at,snapshot_path) VALUES(?,?,?,?,?)",
                (barcode, student_id, now(), due, snapshot_name))

    return {
        "matched": True,
        "barcode": barcode,
        "title": title,
        "student_name": student["name"],
        "due_at": due,
        "already_borrowed": bool(existing),
        "snapshot": snapshot_name,
        "box": book_match["box"],
        "width": result["width"],
        "height": result["height"]
    }


# ---------- Dashboard & Recent Events ----------

@router.get("/events/recent")
def recent_events(_=Depends(current_staff)):
    return query("""
        SELECT e.id, e.kind, e.source, e.at, s.name, s.student_code
        FROM events e JOIN students s ON s.id = e.student_id
        ORDER BY e.id DESC LIMIT 50
    """)


@router.get("/dashboard")
def dashboard(_=Depends(current_staff)):
    today = now()
    open_loans = query("SELECT COUNT(*) AS n FROM loans WHERE returned_at IS NULL")[0]["n"]
    overdue = query("SELECT COUNT(*) AS n FROM loans WHERE returned_at IS NULL AND due_at < ?", (today,))[0]["n"]
    students = query("SELECT COUNT(*) AS n FROM students WHERE active = 1")[0]["n"]
    unattended = query("SELECT COUNT(*) AS n FROM unattended_books WHERE status = 'unreviewed'")[0]["n"]
    return {
        "inside": len(inside_ids()),
        "open_loans": open_loans,
        "overdue": overdue,
        "students": students,
        "unattended_books": unattended,
    }