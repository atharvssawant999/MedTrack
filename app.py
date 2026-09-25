from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)

from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv

import os
import json
import sqlite3
from datetime import datetime


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "medtrack-development-secret-key"
)


# =========================================================
# PROJECT PATHS
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_FILE = os.path.join(
    BASE_DIR,
    "medtrack.db"
)

OLD_USERS_FILE = os.path.join(
    BASE_DIR,
    "users.json"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    """
    Create and return a SQLite database connection.
    """

    connection = sqlite3.connect(DATABASE_FILE)

    # Allows us to access columns like:
    # user["name"]
    connection.row_factory = sqlite3.Row

    return connection


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_database():
    """
    Create all required MedTrack database tables.
    """

    connection = get_db()

    try:

        # -------------------------------------------------
        # USERS TABLE
        # -------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'patient',
                created_at TEXT NOT NULL
            )
        """)


        # -------------------------------------------------
        # APPOINTMENTS TABLE
        # -------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                patient_id INTEGER NOT NULL,

                doctor_id INTEGER,

                doctor_name TEXT NOT NULL,

                appointment_date TEXT NOT NULL,

                appointment_time TEXT NOT NULL,

                department TEXT NOT NULL,

                status TEXT NOT NULL DEFAULT 'Confirmed',

                created_at TEXT NOT NULL,

                FOREIGN KEY (patient_id)
                    REFERENCES users(id),

                FOREIGN KEY (doctor_id)
                    REFERENCES users(id)
            )
        """)


        # -------------------------------------------------
        # MEDICAL RECORDS TABLE
        # -------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS medical_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                patient_id INTEGER NOT NULL,

                title TEXT NOT NULL,

                details TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY (patient_id)
                    REFERENCES users(id)
            )
        """)


        # -------------------------------------------------
        # DIAGNOSIS TABLE
        # -------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                patient_id INTEGER NOT NULL,

                doctor_id INTEGER,

                diagnosis TEXT NOT NULL,

                notes TEXT,

                created_at TEXT NOT NULL,

                FOREIGN KEY (patient_id)
                    REFERENCES users(id),

                FOREIGN KEY (doctor_id)
                    REFERENCES users(id)
            )
        """)



        # -------------------------------------------------
        # PRESCRIPTIONS TABLE
        # -------------------------------------------------

        connection.execute("""
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_id INTEGER NOT NULL,
                medication_name TEXT NOT NULL,
                dosage TEXT NOT NULL,
                frequency TEXT NOT NULL,
                duration TEXT NOT NULL,
                instructions TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES users(id),
                FOREIGN KEY (doctor_id) REFERENCES users(id)
            )
        """)

        connection.commit()

    finally:

        connection.close()


# =========================================================
# MIGRATE OLD USERS.JSON
# =========================================================

def migrate_old_users():
    """
    If the old users.json exists, copy its users into SQLite.

    This allows previously registered accounts to continue
    working after switching from JSON to SQLite.
    """

    if not os.path.exists(OLD_USERS_FILE):
        return


    try:

        with open(
            OLD_USERS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            old_users = json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ):

        return


    if not isinstance(old_users, list):
        return


    connection = get_db()

    try:

        for user in old_users:

            name = user.get("name", "").strip()

            email = user.get(
                "email",
                ""
            ).strip().lower()

            phone = user.get(
                "phone",
                ""
            ).strip()

            password = user.get(
                "password",
                ""
            )

            role = user.get(
                "role",
                "patient"
            ).strip().lower()


            if not name or not email or not password:
                continue


            if role not in [
                "patient",
                "doctor"
            ]:

                role = "patient"


            # Insert only if email does not already exist.
            connection.execute(
                """
                INSERT OR IGNORE INTO users
                (
                    name,
                    email,
                    phone,
                    password,
                    role,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    phone,
                    password,
                    role,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )


        connection.commit()

    finally:

        connection.close()


# =========================================================
# LOGIN REQUIRED HELPER
# =========================================================

def is_logged_in():
    """
    Check whether a user is logged in.
    """

    return session.get("logged_in") is True


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    # If already logged in,
    # don't show login page again.

    if is_logged_in():

        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # POST LOGIN
    # -----------------------------------------------------

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        password = request.form.get(
            "password",
            ""
        )


        role = request.form.get(
            "role",
            "patient"
        ).strip().lower()


        # -------------------------------------------------
        # BASIC VALIDATION
        # -------------------------------------------------

        if not email or not password:

            flash(
                "Please enter your email and password.",
                "error"
            )

            return render_template(
                "login.html"
            )


        if role not in [
            "patient",
            "doctor"
        ]:

            role = "patient"


        # -------------------------------------------------
        # FIND USER
        # -------------------------------------------------

        connection = get_db()

        try:

            user = connection.execute(
                """
                SELECT *
                FROM users
                WHERE lower(email) = ?
                AND lower(role) = ?
                """,
                (
                    email,
                    role
                )
            ).fetchone()

        finally:

            connection.close()


        # -------------------------------------------------
        # USER NOT FOUND
        # -------------------------------------------------

        if user is None:

            flash(
                "Account not found. Please check your email and account type.",
                "error"
            )

            return render_template(
                "login.html"
            )


        # -------------------------------------------------
        # PASSWORD CHECK
        # -------------------------------------------------

        if not check_password_hash(
            user["password"],
            password
        ):

            flash(
                "Incorrect password. Please try again.",
                "error"
            )

            return render_template(
                "login.html"
            )


        # -------------------------------------------------
        # LOGIN SUCCESS
        # -------------------------------------------------

        session.clear()


        session["logged_in"] = True

        session["user_id"] = user["id"]

        session["name"] = user["name"]

        session["email"] = user["email"]

        session["role"] = user["role"]


        flash(
            f"Welcome back, {user['name']}!",
            "success"
        )


        # Both patient and doctor go to
        # /dashboard.
        #
        # The dashboard decides which UI
        # should be displayed.

        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # GET LOGIN PAGE
    # -----------------------------------------------------

    return render_template(
        "login.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    # -----------------------------------------------------
    # POST REGISTER
    # -----------------------------------------------------

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()


        email = request.form.get(
            "email",
            ""
        ).strip().lower()


        phone = request.form.get(
            "phone",
            ""
        ).strip()


        password = request.form.get(
            "password",
            ""
        )


        role = request.form.get(
            "role",
            "patient"
        ).strip().lower()


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not name or not email or not password:

            flash(
                "Please fill in all required fields.",
                "error"
            )

            return render_template(
                "register.html"
            )


        if role not in [
            "patient",
            "doctor"
        ]:

            role = "patient"


        # -------------------------------------------------
        # CHECK EMAIL
        # -------------------------------------------------

        connection = get_db()

        try:

            existing_user = connection.execute(
                """
                SELECT id
                FROM users
                WHERE lower(email) = ?
                """,
                (email,)
            ).fetchone()


            if existing_user:

                flash(
                    "An account with this email already exists.",
                    "error"
                )

                return render_template(
                    "register.html"
                )


            # -------------------------------------------------
            # HASH PASSWORD
            # -------------------------------------------------

            hashed_password = generate_password_hash(
                password
            )


            # -------------------------------------------------
            # CREATE USER
            # -------------------------------------------------

            cursor = connection.execute(
                """
                INSERT INTO users
                (
                    name,
                    email,
                    phone,
                    password,
                    role,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    phone,
                    hashed_password,
                    role,
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )
            )


            user_id = cursor.lastrowid


            connection.commit()


        except sqlite3.IntegrityError:

            connection.rollback()

            flash(
                "An account with this email already exists.",
                "error"
            )

            return render_template(
                "register.html"
            )

        finally:

            connection.close()


        # -------------------------------------------------
        # AUTOMATIC LOGIN
        # -------------------------------------------------
        #
        # After registration, user is directly logged in.
        # This makes the website flow seamless.

        session.clear()


        session["logged_in"] = True

        session["user_id"] = user_id

        session["name"] = name

        session["email"] = email

        session["role"] = role


        flash(
            "Registration successful! Welcome to MedTrack.",
            "success"
        )


        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # GET REGISTER PAGE
    # -----------------------------------------------------

    return render_template(
        "register.html"
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    # -----------------------------------------------------
    # PROTECT DASHBOARD
    # -----------------------------------------------------

    if not is_logged_in():

        flash(
            "Please login to access your dashboard.",
            "error"
        )

        return redirect(
            url_for("login")
        )


    # -----------------------------------------------------
    # CURRENT USER
    # -----------------------------------------------------

    user = {
        "id": session.get("user_id"),
        "name": session.get("name"),
        "email": session.get("email"),
        "role": session.get("role")
    }


    connection = get_db()


    try:

        prescriptions = connection.execute(
            """
            SELECT prescriptions.*, patients.name AS patient_name,
                   doctors.name AS doctor_name
            FROM prescriptions
            JOIN users AS patients ON prescriptions.patient_id = patients.id
            JOIN users AS doctors ON prescriptions.doctor_id = doctors.id
            WHERE prescriptions.patient_id = ?
               OR prescriptions.doctor_id = ?
            ORDER BY prescriptions.created_at DESC, prescriptions.id DESC
            """,
            (user["id"], user["id"])
        ).fetchall()



        # =================================================
        # PATIENT DASHBOARD
        # =================================================

        if user["role"] == "patient":

            # ---------------------------------------------
            # APPOINTMENTS
            # ---------------------------------------------

            appointments = connection.execute(
                """
                SELECT
                    *
                FROM appointments
                WHERE patient_id = ?
                ORDER BY
                    appointment_date ASC,
                    appointment_time ASC
                """,
                (user["id"],)
            ).fetchall()


            # ---------------------------------------------
            # MEDICAL RECORDS
            # ---------------------------------------------

            records = connection.execute(
                """
                SELECT
                    *
                FROM medical_records
                WHERE patient_id = ?
                ORDER BY
                    created_at DESC
                """,
                (user["id"],)
            ).fetchall()


            # ---------------------------------------------
            # DIAGNOSES
            # ---------------------------------------------

            diagnoses = connection.execute(
                """
                SELECT
                    *
                FROM diagnoses
                WHERE patient_id = ?
                ORDER BY
                    created_at DESC
                """,
                (user["id"],)
            ).fetchall()


            # ---------------------------------------------
            # STATS
            # ---------------------------------------------

            stats = {

                "appointments": len(appointments),

                "records": len(records),

                "diagnoses": len(diagnoses)

            }


            return render_template(
                "dashboard.html",
                user=user,
                stats=stats,
                appointments=appointments,
                records=records,
                diagnoses=diagnoses,
                prescriptions=prescriptions,
                patients=[]
            )


        # =================================================
        # DOCTOR DASHBOARD
        # =================================================

        else:

            # ---------------------------------------------
            # PATIENT LIST
            # ---------------------------------------------

            patients = connection.execute(
                """
                SELECT
                    id,
                    name,
                    email,
                    phone,
                    created_at
                FROM users
                WHERE role = 'patient'
                ORDER BY name ASC
                """
            ).fetchall()


            # ---------------------------------------------
            # DOCTOR APPOINTMENTS
            # ---------------------------------------------
            #
            # We check both:
            #
            # doctor_id
            #
            # OR
            #
            # doctor_name
            #
            # This allows appointments to work even when
            # the patient typed the doctor's name manually.

            doctor_name = user["name"].strip().lower()


            appointments = connection.execute(
                """
                SELECT
                    appointments.*,
                    users.name AS patient_name,
                    users.email AS patient_email
                FROM appointments
                JOIN users
                    ON appointments.patient_id = users.id
                WHERE
                    appointments.doctor_id = ?
                    OR lower(appointments.doctor_name) = ?
                ORDER BY
                    appointments.appointment_date ASC,
                    appointments.appointment_time ASC
                """,
                (
                    user["id"],
                    doctor_name
                )
            ).fetchall()


            # ---------------------------------------------
            # DIAGNOSIS COUNT
            # ---------------------------------------------

            diagnosis_count = connection.execute(
                """
                SELECT COUNT(*)
                AS total
                FROM diagnoses
                WHERE doctor_id = ?
                """,
                (user["id"],)
            ).fetchone()["total"]


            # ---------------------------------------------
            # STATS
            # ---------------------------------------------

            stats = {

                "patients": len(patients),

                "appointments": len(appointments),

                "diagnoses": diagnosis_count

            }


            return render_template(
                "dashboard.html",
                user=user,
                stats=stats,
                appointments=appointments,
                records=[],
                diagnoses=[],
                prescriptions=prescriptions,
                patients=patients
            )


    finally:

        connection.close()


# =========================================================
# APPOINTMENTS PAGE
# =========================================================

@app.route("/appointments")
def appointments():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db()

    try:
        doctors = connection.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE role = 'doctor'
            ORDER BY name ASC
            """
        ).fetchall()

        if session.get("role") == "patient":
            appointment_list = connection.execute(
                """
                SELECT *
                FROM appointments
                WHERE patient_id = ?
                ORDER BY appointment_date ASC, appointment_time ASC
                """,
                (session["user_id"],)
            ).fetchall()
        else:
            doctor_name = (session.get("name") or "").strip().lower()
            appointment_list = connection.execute(
                """
                SELECT
                    appointments.*,
                    users.name AS patient_name,
                    users.email AS patient_email
                FROM appointments
                JOIN users ON appointments.patient_id = users.id
                WHERE appointments.doctor_id = ?
                   OR lower(appointments.doctor_name) = ?
                ORDER BY appointment_date ASC, appointment_time ASC
                """,
                (session["user_id"], doctor_name)
            ).fetchall()

        return render_template(
            "appointments.html",
            user={
                "id": session.get("user_id"),
                "name": session.get("name"),
                "email": session.get("email"),
                "role": session.get("role")
            },
            doctors=doctors,
            appointments=appointment_list,
            now_date=datetime.now().strftime("%Y-%m-%d")
        )

    finally:
        connection.close()


# =========================================================
# BOOK APPOINTMENT
# =========================================================

@app.route(
    "/appointments/book",
    methods=["POST"]
)
def book_appointment():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "patient":
        flash("Only patients can book appointments.", "error")
        return redirect(url_for("appointments"))

    doctor_id_raw = request.form.get("doctor_id", "").strip()
    doctor_name = request.form.get("doctor_name", "").strip()
    department = request.form.get("department", "").strip()
    appointment_date = request.form.get("appointment_date", "").strip()
    appointment_time = request.form.get("appointment_time", "").strip()

    if not department or not appointment_date or not appointment_time:
        flash("Please fill in all appointment details.", "error")
        return redirect(url_for("appointments"))

    try:
        selected_date = datetime.strptime(appointment_date, "%Y-%m-%d").date()
        selected_time = datetime.strptime(appointment_time, "%H:%M").time()
    except ValueError:
        flash("Please enter a valid appointment date and time.", "error")
        return redirect(url_for("appointments"))

    now = datetime.now()
    if selected_date < now.date() or (selected_date == now.date() and selected_time <= now.time()):
        flash("Appointment must be scheduled for a future date and time.", "error")
        return redirect(url_for("appointments"))

    connection = get_db()

    try:
        doctor = None

        if doctor_id_raw.isdigit():
            doctor = connection.execute(
                """
                SELECT id, name
                FROM users
                WHERE id = ? AND role = 'doctor'
                """,
                (int(doctor_id_raw),)
            ).fetchone()

        if doctor is None and doctor_name:
            doctor = connection.execute(
                """
                SELECT id, name
                FROM users
                WHERE role = 'doctor' AND lower(name) = ?
                """,
                (doctor_name.lower(),)
            ).fetchone()

        if doctor is None:
            flash("Please select a valid doctor.", "error")
            return redirect(url_for("appointments"))

        doctor_id = doctor["id"]
        doctor_name = doctor["name"]

        existing = connection.execute(
            """
            SELECT id
            FROM appointments
            WHERE doctor_id = ?
              AND appointment_date = ?
              AND appointment_time = ?
              AND status NOT IN ('Cancelled', 'Completed')
            LIMIT 1
            """,
            (doctor_id, appointment_date, appointment_time)
        ).fetchone()

        if existing:
            flash("That time slot is already booked. Please choose another time.", "error")
            return redirect(url_for("appointments"))

        connection.execute(
            """
            INSERT INTO appointments
            (patient_id, doctor_id, doctor_name, appointment_date, appointment_time, department, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                doctor_id,
                doctor_name,
                appointment_date,
                appointment_time,
                department,
                "Confirmed",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        connection.commit()

    finally:
        connection.close()

    flash("Appointment booked successfully!", "success")
    return redirect(url_for("appointments"))


# =========================================================
# CANCEL APPOINTMENT
# =========================================================

@app.route("/appointments/cancel/<int:appointment_id>", methods=["POST"])
def cancel_appointment(appointment_id):

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db()

    try:
        appointment = connection.execute(
            "SELECT * FROM appointments WHERE id = ?",
            (appointment_id,)
        ).fetchone()

        if appointment is None:
            flash("Appointment not found.", "error")
            return redirect(url_for("appointments"))

        allowed = (
            session.get("role") == "patient"
            and appointment["patient_id"] == session.get("user_id")
        )

        if not allowed:
            flash("You are not allowed to cancel this appointment.", "error")
            return redirect(url_for("appointments"))

        if appointment["status"] in ("Cancelled", "Completed"):
            flash("This appointment can no longer be cancelled.", "error")
            return redirect(url_for("appointments"))

        connection.execute(
            "UPDATE appointments SET status = 'Cancelled' WHERE id = ?",
            (appointment_id,)
        )
        connection.commit()

    finally:
        connection.close()

    flash("Appointment cancelled successfully.", "success")
    return redirect(url_for("appointments"))


# =========================================================
# UPDATE APPOINTMENT STATUS - DOCTOR
# =========================================================

@app.route("/appointments/status/<int:appointment_id>", methods=["POST"])
def update_appointment_status(appointment_id):

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "doctor":
        flash("Only doctors can update appointment status.", "error")
        return redirect(url_for("appointments"))

    new_status = request.form.get("status", "").strip()
    if new_status not in {"Confirmed", "Completed", "Cancelled"}:
        flash("Invalid appointment status.", "error")
        return redirect(url_for("appointments"))

    connection = get_db()

    try:
        appointment = connection.execute(
            """
            SELECT id
            FROM appointments
            WHERE id = ?
              AND (doctor_id = ? OR lower(doctor_name) = ?)
            """,
            (appointment_id, session["user_id"], (session.get("name") or "").strip().lower())
        ).fetchone()

        if appointment is None:
            flash("Appointment not found or access denied.", "error")
            return redirect(url_for("appointments"))

        connection.execute(
            "UPDATE appointments SET status = ? WHERE id = ?",
            (new_status, appointment_id)
        )
        connection.commit()

    finally:
        connection.close()

    flash("Appointment status updated.", "success")
    return redirect(url_for("appointments"))


# =========================================================
# MEDICAL RECORDS
# =========================================================

@app.route("/medical-records")
def medical_records():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db()

    try:
        user_id = session["user_id"]
        role = session.get("role")

        if role == "patient":
            records = connection.execute(
                '''
                SELECT id, patient_id, title, details, created_at
                FROM medical_records
                WHERE patient_id = ?
                ORDER BY created_at DESC, id DESC
                ''',
                (user_id,)
            ).fetchall()
        else:
            records = connection.execute(
                '''
                SELECT DISTINCT
                    medical_records.id,
                    medical_records.patient_id,
                    medical_records.title,
                    medical_records.details,
                    medical_records.created_at
                FROM medical_records
                JOIN appointments
                    ON appointments.patient_id = medical_records.patient_id
                WHERE appointments.doctor_id = ?
                   OR lower(appointments.doctor_name) = lower(?)
                ORDER BY medical_records.created_at DESC, medical_records.id DESC
                ''',
                (user_id, session.get("name", "").strip())
            ).fetchall()
    finally:
        connection.close()

    user = {
        "id": session.get("user_id"),
        "name": session.get("name"),
        "email": session.get("email"),
        "role": session.get("role")
    }

    return render_template(
        "medical_records.html",
        user=user,
        records=records
    )


@app.route("/medical-records/add", methods=["POST"])
def add_medical_record():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "patient":
        flash("Only patients can add medical records.", "error")
        return redirect(url_for("medical_records"))

    title = request.form.get("title", "").strip()
    details = request.form.get("details", "").strip()

    if not title:
        flash("Please enter a record title.", "error")
        return redirect(url_for("medical_records"))

    if len(title) > 120:
        flash("Record title is too long.", "error")
        return redirect(url_for("medical_records"))

    connection = get_db()

    try:
        connection.execute(
            '''
            INSERT INTO medical_records
            (patient_id, title, details, created_at)
            VALUES (?, ?, ?, ?)
            ''',
            (
                session["user_id"],
                title,
                details,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        connection.commit()
    finally:
        connection.close()

    flash("Medical record added successfully.", "success")
    return redirect(url_for("medical_records"))


@app.route("/medical-records/delete/<int:record_id>", methods=["POST"])
def delete_medical_record(record_id):

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "patient":
        flash("Only patients can delete their medical records.", "error")
        return redirect(url_for("medical_records"))

    connection = get_db()

    try:
        record = connection.execute(
            '''
            SELECT id
            FROM medical_records
            WHERE id = ? AND patient_id = ?
            ''',
            (record_id, session["user_id"])
        ).fetchone()

        if record is None:
            flash("Medical record not found.", "error")
            return redirect(url_for("medical_records"))

        connection.execute(
            "DELETE FROM medical_records WHERE id = ? AND patient_id = ?",
            (record_id, session["user_id"])
        )
        connection.commit()
    finally:
        connection.close()

    flash("Medical record deleted.", "success")
    return redirect(url_for("medical_records"))


# =========================================================
# PRESCRIPTIONS
# =========================================================

@app.route("/prescriptions")
def prescriptions():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    connection = get_db()

    try:
        user_id = session["user_id"]
        role = session.get("role")

        if role == "doctor":
            prescription_rows = connection.execute(
                """
                SELECT prescriptions.*, patients.name AS patient_name,
                       doctors.name AS doctor_name
                FROM prescriptions
                JOIN users AS patients ON prescriptions.patient_id = patients.id
                JOIN users AS doctors ON prescriptions.doctor_id = doctors.id
                WHERE prescriptions.doctor_id = ?
                ORDER BY prescriptions.created_at DESC, prescriptions.id DESC
                """,
                (user_id,)
            ).fetchall()

            patients = connection.execute(
                """
                SELECT DISTINCT users.id, users.name, users.email
                FROM users
                JOIN appointments ON appointments.patient_id = users.id
                WHERE users.role = 'patient'
                  AND (appointments.doctor_id = ?
                       OR lower(appointments.doctor_name) = lower(?))
                ORDER BY users.name ASC
                """,
                (user_id, session.get("name", "").strip())
            ).fetchall()
        else:
            prescription_rows = connection.execute(
                """
                SELECT prescriptions.*, patients.name AS patient_name,
                       doctors.name AS doctor_name
                FROM prescriptions
                JOIN users AS patients ON prescriptions.patient_id = patients.id
                JOIN users AS doctors ON prescriptions.doctor_id = doctors.id
                WHERE prescriptions.patient_id = ?
                ORDER BY prescriptions.created_at DESC, prescriptions.id DESC
                """,
                (user_id,)
            ).fetchall()
            patients = []

    finally:
        connection.close()

    user = {
        "id": session.get("user_id"),
        "name": session.get("name"),
        "email": session.get("email"),
        "role": session.get("role")
    }

    return render_template(
        "prescriptions.html",
        user=user,
        prescriptions=prescription_rows,
        patients=patients
    )


@app.route("/prescriptions/add", methods=["POST"])
def add_prescription():

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "doctor":
        flash("Only doctors can issue prescriptions.", "error")
        return redirect(url_for("prescriptions"))

    patient_id = request.form.get("patient_id", "").strip()
    medication_name = request.form.get("medication_name", "").strip()
    dosage = request.form.get("dosage", "").strip()
    frequency = request.form.get("frequency", "").strip()
    duration = request.form.get("duration", "").strip()
    instructions = request.form.get("instructions", "").strip()

    if not all([patient_id, medication_name, dosage, frequency, duration]):
        flash("Please fill in all required prescription details.", "error")
        return redirect(url_for("prescriptions"))

    try:
        patient_id = int(patient_id)
    except ValueError:
        flash("Invalid patient.", "error")
        return redirect(url_for("prescriptions"))

    connection = get_db()

    try:
        patient = connection.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'patient'",
            (patient_id,)
        ).fetchone()

        if patient is None:
            flash("Patient not found.", "error")
            return redirect(url_for("prescriptions"))

        appointment = connection.execute(
            """
            SELECT id FROM appointments
            WHERE patient_id = ?
              AND (doctor_id = ? OR lower(doctor_name) = lower(?))
            LIMIT 1
            """,
            (patient_id, session["user_id"], session.get("name", "").strip())
        ).fetchone()

        if appointment is None:
            flash("You can issue a prescription only to one of your patients.", "error")
            return redirect(url_for("prescriptions"))

        connection.execute(
            """
            INSERT INTO prescriptions
            (patient_id, doctor_id, medication_name, dosage, frequency,
             duration, instructions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id, session["user_id"], medication_name, dosage,
                frequency, duration, instructions,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        connection.commit()

    finally:
        connection.close()

    flash("Prescription issued successfully.", "success")
    return redirect(url_for("prescriptions"))


@app.route("/prescriptions/delete/<int:prescription_id>", methods=["POST"])
def delete_prescription(prescription_id):

    if not is_logged_in():
        flash("Please login first.", "error")
        return redirect(url_for("login"))

    if session.get("role") != "doctor":
        flash("Only doctors can delete prescriptions.", "error")
        return redirect(url_for("prescriptions"))

    connection = get_db()

    try:
        result = connection.execute(
            "DELETE FROM prescriptions WHERE id = ? AND doctor_id = ?",
            (prescription_id, session["user_id"])
        )
        if result.rowcount == 0:
            flash("Prescription not found.", "error")
        else:
            connection.commit()
            flash("Prescription deleted.", "success")
    finally:
        connection.close()

    return redirect(url_for("prescriptions"))


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out successfully.",
        "success"
    )


    return redirect(
        url_for("home")
    )


# =========================================================
# OPTIONAL: PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if not is_logged_in():

        flash(
            "Please login first.",
            "error"
        )

        return redirect(
            url_for("login")
        )


    connection = get_db()

    try:

        user = connection.execute(
            """
            SELECT
                id,
                name,
                email,
                phone,
                role,
                created_at
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],)
        ).fetchone()

        prescriptions = connection.execute(
            """
            SELECT
                prescriptions.*,
                patients.name AS patient_name,
                doctors.name AS doctor_name
            FROM prescriptions
            JOIN users AS patients
                ON prescriptions.patient_id = patients.id
            JOIN users AS doctors
                ON prescriptions.doctor_id = doctors.id
            WHERE prescriptions.patient_id = ?
               OR prescriptions.doctor_id = ?
            ORDER BY prescriptions.created_at DESC, prescriptions.id DESC
            """,
            (session["user_id"], session["user_id"])
        ).fetchall()


    finally:

        connection.close()


    if user is None:

        session.clear()

        flash(
            "User account could not be found.",
            "error"
        )

        return redirect(
            url_for("login")
        )


    return render_template(
        "dashboard.html",
        user=dict(user),
        stats={
            "appointments": 0,
            "records": 0,
            "diagnoses": 0,
            "patients": 0
        },
        appointments=[],
        records=[],
        diagnoses=[],
        prescriptions=prescriptions,
        patients=[]
    )


# =========================================================
# 404 ERROR
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <!DOCTYPE html>

    <html>

    <head>

        <title>404 - MedTrack</title>

        <style>

            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 80px;
                background: #f5f7fb;
            }

            h1 {
                font-size: 50px;
                color: #2563eb;
            }

            a {
                color: #2563eb;
                text-decoration: none;
            }

        </style>

    </head>

    <body>

        <h1>404</h1>

        <h2>Page Not Found</h2>

        <p>
            The page you requested does not exist.
        </p>

        <br>

        <a href="/">
            ← Go back to MedTrack
        </a>

    </body>

    </html>
    """, 404


# =========================================================
# 500 ERROR
# =========================================================

@app.errorhandler(500)
def internal_server_error(error):

    return """
    <!DOCTYPE html>

    <html>

    <head>

        <title>500 - MedTrack</title>

        <style>

            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 80px;
                background: #f5f7fb;
            }

            h1 {
                font-size: 50px;
                color: #dc2626;
            }

        </style>

    </head>

    <body>

        <h1>500</h1>

        <h2>Internal Server Error</h2>

        <p>
            Something went wrong on the server.
        </p>

        <br>

        <a href="/">
            ← Go back to MedTrack
        </a>

    </body>

    </html>
    """, 500


# =========================================================
# INITIALIZE DATABASE
# =========================================================
# This must run when Gunicorn/Render imports app.py.
# Otherwise the SQLite tables do not exist on Render.

init_database()
migrate_old_users()


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    print("")
    print("========================================")
    print("        MEDTRACK APPLICATION")
    print("========================================")
    print("")
    print("Database:", DATABASE_FILE)
    print("")
    print("Home:")
    print("http://127.0.0.1:5000/")
    print("")
    print("Login:")
    print("http://127.0.0.1:5000/login")
    print("")
    print("Register:")
    print("http://127.0.0.1:5000/register")
    print("")
    print("Dashboard:")
    print("http://127.0.0.1:5000/dashboard")
    print("")
    print("========================================")
    print("")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )