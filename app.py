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
                patients=patients
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

    # -----------------------------------------------------
    # LOGIN CHECK
    # -----------------------------------------------------

    if not is_logged_in():

        flash(
            "Please login first.",
            "error"
        )

        return redirect(
            url_for("login")
        )


    # -----------------------------------------------------
    # ONLY PATIENT CAN BOOK
    # -----------------------------------------------------

    if session.get("role") != "patient":

        flash(
            "Only patients can book appointments.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # FORM DATA
    # -----------------------------------------------------

    doctor_name = request.form.get(
        "doctor_name",
        ""
    ).strip()


    department = request.form.get(
        "department",
        ""
    ).strip()


    appointment_date = request.form.get(
        "appointment_date",
        ""
    ).strip()


    appointment_time = request.form.get(
        "appointment_time",
        ""
    ).strip()


    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------

    if (
        not doctor_name
        or not department
        or not appointment_date
        or not appointment_time
    ):

        flash(
            "Please fill in all appointment details.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # DATE VALIDATION
    # -----------------------------------------------------

    try:

        selected_date = datetime.strptime(
            appointment_date,
            "%Y-%m-%d"
        ).date()


        today = datetime.now().date()


        if selected_date < today:

            flash(
                "Appointment date cannot be in the past.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

    except ValueError:

        flash(
            "Invalid appointment date.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    # -----------------------------------------------------
    # TRY TO FIND DOCTOR ACCOUNT
    # -----------------------------------------------------

    connection = get_db()

    try:

        doctor = connection.execute(
            """
            SELECT id
            FROM users
            WHERE role = 'doctor'
            AND lower(name) = ?
            """,
            (
                doctor_name.lower(),
            )
        ).fetchone()


        doctor_id = None

        if doctor:

            doctor_id = doctor["id"]


        # -------------------------------------------------
        # CREATE APPOINTMENT
        # -------------------------------------------------

        connection.execute(
            """
            INSERT INTO appointments
            (
                patient_id,
                doctor_id,
                doctor_name,
                appointment_date,
                appointment_time,
                department,
                status,
                created_at
            )
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
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
        )


        connection.commit()


    finally:

        connection.close()


    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    flash(
        "Appointment booked successfully!",
        "success"
    )


    return redirect(
        url_for("dashboard")
    )


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