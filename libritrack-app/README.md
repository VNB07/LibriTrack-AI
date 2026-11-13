# LibriTrack-AI (Version 1)

Staff web app for library entry logging, students, books and loans. Face recognition uses only photos of students who have consented.

## Run locally

Requires Python 3.10+. The face_recognition library needs dlib, which needs CMake and a C++ compiler installed first.

    cd backend
    pip install -r requirements.txt
    python seed.py                 # creates the first admin account
    uvicorn app.main:app --reload

Then open http://localhost:8000 and log in with the admin details printed by seed.py.

Set LIBRITRACK_SECRET and LIBRITRACK_ADMIN_PASSWORD as environment variables before running anything real.

## Structure

- backend/app: FastAPI app (main, database, security, routes)
- ml: face embedding and matching (face_recognition, replaceable behind this module)
- frontend: HTML, CSS and JavaScript, served by FastAPI

## Covered in version 1

Staff login, student management with recorded consent, face photo upload and deletion, consent withdrawal, a list of each staff member's uploads, book management, checkout and return, face-based entry at a camera endpoint, manual entry and exit, and a dashboard.

## Not yet covered (next milestone)

Automatic exit timeout, due and overdue reminder emails, audit logs, admin role management UI, camera registry, reports and CSV import, barcode camera scanning in the browser.
