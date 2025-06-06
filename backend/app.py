# backend/app.py

import os
import traceback
from dotenv import load_dotenv

# ─── 1) Load environment variables BEFORE anything else ─────────────────────────
load_dotenv()
print("→ DEBUG: SQLALCHEMY_DATABASE_URI =", os.getenv("DATABASE_URL"))

from flask import Flask, request, jsonify, send_file
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
from datetime import timedelta
import uuid
from urllib.parse import urljoin
from io import BytesIO

# ─── 2) Flask app setup ────────────────────────────────────────────────────────
app = Flask(__name__)
bcrypt = Bcrypt(app)

# ─── 2a) Enable CORS for all /api/* routes ─────────────────────────────────────
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ─── 3) Configuration ──────────────────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "super-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=7)

VERCEL_BLOB_UPLOAD_URL = os.getenv("VERCEL_BLOB_UPLOAD_URL")
VERCEL_BLOB_TOKEN = os.getenv("VERCEL_BLOB_TOKEN")

# ─── 4) Sanity checks ───────────────────────────────────────────────────────────
if not app.config["SQLALCHEMY_DATABASE_URI"]:
    raise RuntimeError("Missing DATABASE_URL in .env")

if not VERCEL_BLOB_UPLOAD_URL or not VERCEL_BLOB_TOKEN:
    raise RuntimeError("Missing VERCEL_BLOB_UPLOAD_URL or VERCEL_BLOB_TOKEN in .env")

# ─── 5) Initialize SQLAlchemy & JWT ─────────────────────────────────────────────
db = SQLAlchemy(app)
jwt = JWTManager(app)


# ─── 6) Models ─────────────────────────────────────────────────────────────────

class User(db.Model):
    """
    Maps to 'users' table.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False, default="user")
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.current_timestamp(), onupdate=db.func.current_timestamp()
    )

    # Relationship: files uploaded by this user
    files = db.relationship("File", backref="uploader", lazy=True)

    def to_dict(self):
        """
        Safely convert to dict. If created_at or updated_at is None,
        return None (instead of calling .isoformat() on None).
        """
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class File(db.Model):
    """
    Maps to 'files' table.
    """
    __tablename__ = "files"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.Text, nullable=False)
    uploaded_by = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp(),
        nullable=False
    )
    # It’s possible your existing DB does not yet have this column.
    # We always read via getattr(f, "edited", False) to default to False if missing.
    edited = db.Column(db.Boolean, nullable=False, default=False)


# ─── 7) Create tables if they don’t exist ───────────────────────────────────────
@app.before_first_request
def create_tables():
    db.create_all()


# ─── 8) Utility: Get current user from JWT ─────────────────────────────────────
def get_current_user():
    user_id = get_jwt_identity()
    if user_id is None:
        return None
    return User.query.get(user_id)


# ─── 9) Ping endpoint (diagnostic) ─────────────────────────────────────────────
@app.route("/api/ping", methods=["GET"])
def ping():
    return jsonify({"database_uri": app.config.get("SQLALCHEMY_DATABASE_URI")}), 200


# ─── 10) Register endpoint ─────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    """
    POST /api/register
    Expects JSON: { name, email, password, role }
    """
    data = request.get_json()
    if not data:
        return jsonify({"msg": "Missing JSON in request"}), 400

    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    role = data.get("role", "user").strip().lower()

    if not name or not email or not password:
        return jsonify({"msg": "Name, email, and password are required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "Email already registered"}), 409

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    new_user = User(name=name, email=email, password_hash=pw_hash, role=role)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"msg": "User registered successfully."}), 201


# ─── 11) Login endpoint ─────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    """
    POST /api/login
    Expects JSON: { email, password }
    Returns: { msg, access_token, refresh_token, role }
    """
    data = request.get_json()
    if not data:
        return jsonify({"msg": "Missing JSON in request"}), 400

    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    if not email or not password:
        return jsonify({"msg": "Email and password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({"msg": "Invalid credentials"}), 401

    access_token = create_access_token(identity=user.id, additional_claims={"role": user.role})
    refresh_token = create_refresh_token(identity=user.id, additional_claims={"role": user.role})

    return jsonify(
        {
            "msg": "Login successful.",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "role": user.role,
        }
    ), 200


# ─── 12) Token refresh endpoint ─────────────────────────────────────────────────
@app.route("/api/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh_token():
    """
    POST /api/refresh
    Uses refresh token to issue a new access token.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    new_access = create_access_token(identity=user.id, additional_claims={"role": user.role})
    return jsonify({"access_token": new_access}), 200


# ─── 13) Password reset endpoint ───────────────────────────────────────────────
@app.route("/api/reset_password", methods=["POST"])
def reset_password():
    """
    POST /api/reset_password
    Expects JSON: { email, new_password }
    """
    data = request.get_json()
    if not data:
        return jsonify({"msg": "Missing JSON in request"}), 400

    email = data.get("email", "").strip().lower()
    new_password = data.get("new_password", "").strip()
    if not email or not new_password:
        return jsonify({"msg": "Email and new_password required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"msg": "User not found"}), 404

    new_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
    user.password_hash = new_hash
    db.session.commit()

    return jsonify({"msg": "Password updated successfully."}), 200


# ─── 14) Upload endpoint (User → Vercel Blob → Save in files table) ──────────
@app.route("/api/upload", methods=["POST"])
@jwt_required()
def upload_file():
    """
    POST /api/upload
    Header: Authorization: Bearer <access_token>
    Multipart form: { 'file': <uploaded PDF or image> }
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found (invalid or missing token)."}), 404

        if "file" not in request.files:
            return jsonify({"msg": "No file part in request (key must be 'file')."}), 400

        file_obj = request.files["file"]
        if file_obj.filename == "":
            return jsonify({"msg": "No file selected."}), 400

        original_filename = secure_filename(file_obj.filename)
        if not original_filename:
            return jsonify({"msg": "Invalid file name."}), 400

        # Generate a unique name for Vercel Blob
        ext = os.path.splitext(original_filename)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_bytes = file_obj.read()

        base_upload_url = VERCEL_BLOB_UPLOAD_URL.rstrip("/") + "/"
        upload_url = urljoin(base_upload_url, unique_name)
        headers = {
            "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
            "Content-Type": file_obj.mimetype,
        }

        resp = requests.put(upload_url, headers=headers, data=file_bytes)
        if resp.status_code not in (200, 201):
            return (
                jsonify({
                    "msg": "Vercel Blob upload failed.",
                    "status_code": resp.status_code,
                    "body": resp.text,
                }),
                502,
            )

        try:
            json_resp = resp.json()
            blob_url = json_resp.get("url", upload_url)
        except ValueError:
            # If Vercel doesn’t return JSON, assume the file is at the same path we PUT to
            blob_url = upload_url

        new_file = File(
            filename=original_filename,
            file_url=blob_url,
            uploaded_by=current_user.id
        )
        db.session.add(new_file)
        db.session.commit()

        return (
            jsonify({
                "msg": "File uploaded successfully.",
                "file": {
                    "id": new_file.id,
                    "filename": new_file.filename,
                    "file_url": new_file.file_url,
                    "uploaded_by": new_file.uploader.name if new_file.uploader else None,
                    "uploaded_at": new_file.uploaded_at.isoformat() if new_file.uploaded_at else None,
                    "edited": getattr(new_file, "edited", False),
                },
            }),
            201,
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error during file upload.",
            "error": str(e)
        }), 500


# ─── 15) Fetch raw PDF bytes for viewing/editing ───────────────────────────────
@app.route("/api/file/<int:file_id>/raw", methods=["GET"])
@jwt_required()
def get_pdf_bytes(file_id):
    """
    GET /api/file/<file_id>/raw
    Returns the raw PDF bytes for the given file_id so the frontend
    can fetch them for viewing/editing.
    Only the uploader (or admin) may fetch it.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        fn = File.query.get(file_id)
        if not fn:
            return jsonify({"msg": "File not found"}), 404

        jwt_data = get_jwt()
        role = jwt_data.get("role") or current_user.role

        # If user is “user”, ensure they own the file
        if role == "user" and fn.uploaded_by != current_user.id:
            return jsonify({"msg": "Forbidden"}), 403

        # Fetch the raw PDF bytes from Vercel Blob
        resp = requests.get(fn.file_url)
        if resp.status_code != 200:
            return jsonify({"msg": "Failed to fetch PDF from storage."}), 502

        pdf_bytes = resp.content
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            download_name=fn.filename
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"msg": "Internal error fetching PDF", "error": str(e)}), 500


# ─── 16) Replace (edit) a file’s contents (user only) ──────────────────────────
@app.route("/api/file/<int:file_id>/edit-pdf", methods=["PUT"])
@jwt_required()
def save_edited_pdf(file_id):
    """
    PUT /api/file/<file_id>/edit-pdf
    Header: Authorization: Bearer <access_token>
    Accepts multipart/form-data with:
       - 'file': <new PDF file>
    Only the original uploader may replace this file.
    Sets edited=True, re-uploads to Vercel Blob, updates DB.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found (invalid or missing token)."}), 404

        fn = File.query.get(file_id)
        if not fn:
            return jsonify({"msg": "File not found"}), 404

        # Only uploader can replace
        if fn.uploaded_by != current_user.id:
            return jsonify({"msg": "Forbidden: cannot edit this file"}), 403

        if "file" not in request.files:
            return jsonify({"msg": "Missing edited PDF in form-data as 'file'"}), 400

        new_file_obj = request.files["file"]
        if new_file_obj.filename == "":
            return jsonify({"msg": "No file selected"}), 400

        original_filename = secure_filename(new_file_obj.filename)
        if not original_filename:
            return jsonify({"msg": "Invalid filename"}), 400

        ext = os.path.splitext(original_filename)[1]  # e.g. “.pdf”
        unique_name = f"{uuid.uuid4().hex}{ext}"
        pdf_bytes = new_file_obj.read()

        base_upload_url = VERCEL_BLOB_UPLOAD_URL.rstrip("/") + "/"
        upload_url = urljoin(base_upload_url, unique_name)
        headers = {
            "Authorization": f"Bearer {VERCEL_BLOB_TOKEN}",
            "Content-Type": new_file_obj.mimetype,  # typically application/pdf
        }

        resp = requests.put(upload_url, headers=headers, data=pdf_bytes)
        if resp.status_code not in (200, 201):
            return jsonify({
                "msg": "Failed to upload edited PDF to blob",
                "status": resp.status_code,
                "body": resp.text
            }), 502

        try:
            js = resp.json()
            blob_url = js.get("url", upload_url)
        except ValueError:
            blob_url = upload_url

        # Update the File record in DB
        fn.filename = original_filename
        fn.file_url = blob_url
        setattr(fn, "edited", True)
        db.session.commit()

        return jsonify({
            "msg": "Edited PDF saved successfully",
            "file": {
                "id": fn.id,
                "filename": fn.filename,
                "file_url": fn.file_url,
                "uploaded_by": fn.uploader.name if fn.uploader else None,
                "uploaded_at": fn.uploaded_at.isoformat() if fn.uploaded_at else None,
                "edited": True,
            }
        }), 200
    except Exception as e:
        traceback.print_exc()
        return jsonify({"msg": "Internal error saving edited PDF", "error": str(e)}), 500


# ─── 17) List files endpoint (admin only) ───────────────────────────────────────
@app.route("/api/files", methods=["GET"])
@jwt_required()
def list_files():
    """
    GET /api/files
    Header: Authorization: Bearer <access_token>
    Only admins can see the list of uploaded files.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        jwt_data = get_jwt()
        role = jwt_data.get("role") or current_user.role
        if role != "admin":
            return jsonify({"msg": "Forbidden: admins only"}), 403

        files = File.query.order_by(File.uploaded_at.desc()).all()
        result = []
        for f in files:
            uploader_name = f.uploader.name if (f.uploader) else "Unknown"
            uploaded_at = f.uploaded_at.isoformat() if f.uploaded_at else None
            result.append({
                "id": f.id,
                "filename": f.filename,
                "file_url": f.file_url,
                "uploaded_by": f.uploaded_by,         # user ID
                "uploader_name": uploader_name,       # uploader’s name
                "uploaded_at": uploaded_at,
                "edited": getattr(f, "edited", False),
            })
        return jsonify(result), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error retrieving files.",
            "error": str(e)
        }), 500


# ─── 18) Get a single file’s details (admin only) ──────────────────────────────
@app.route("/api/file/<int:file_id>", methods=["GET"])
@jwt_required()
def get_file_detail(file_id):
    """
    GET /api/file/<file_id>
    Header: Authorization: Bearer <access_token>
    Only admins can view any single file’s details.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        jwt_data = get_jwt()
        role = jwt_data.get("role") or current_user.role
        if role != "admin":
            return jsonify({"msg": "Forbidden: admins only"}), 403

        file_obj = File.query.get(file_id)
        if not file_obj:
            return jsonify({"msg": "File not found"}), 404

        uploader_name = file_obj.uploader.name if (file_obj.uploader) else "Unknown"
        uploaded_at = file_obj.uploaded_at.isoformat() if file_obj.uploaded_at else None

        return jsonify({
            "id": file_obj.id,
            "filename": file_obj.filename,
            "file_url": file_obj.file_url,
            "uploaded_by": file_obj.uploaded_by,
            "uploader_name": uploader_name,
            "uploaded_at": uploaded_at,
            "edited": getattr(file_obj, "edited", False),
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error retrieving file detail.",
            "error": str(e)
        }), 500


# ─── 19) List user-specific files (user only) ─────────────────────────────────
@app.route("/api/user-files", methods=["GET"])
@jwt_required()
def user_files():
    """
    GET /api/user-files
    Header: Authorization: Bearer <access_token>
    Returns JSON: all files uploaded by the current user.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        files = File.query.filter_by(uploaded_by=current_user.id).order_by(File.uploaded_at.desc()).all()
        result = []
        for f in files:
            uploaded_at = f.uploaded_at.isoformat() if f.uploaded_at else None
            result.append({
                "id": f.id,
                "filename": f.filename,
                "file_url": f.file_url,
                "uploaded_at": uploaded_at,
                "edited": getattr(f, "edited", False),
            })
        return jsonify(result), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error retrieving user files.",
            "error": str(e)
        }), 500


# ─── 20) List only edited user files (user only) ──────────────────────────────
@app.route("/api/user-files/edited", methods=["GET"])
@jwt_required()
def user_edited_files():
    """
    GET /api/user-files/edited
    Header: Authorization: Bearer <access_token>
    Returns JSON: only files uploaded by current user where edited=True.
    """
    try:
        current_user = get_current_user()
        if not current_user:
            return jsonify({"msg": "User not found"}), 404

        all_files = File.query.filter_by(uploaded_by=current_user.id).order_by(File.uploaded_at.desc()).all()
        result = []
        for f in all_files:
            if getattr(f, "edited", False):
                uploaded_at = f.uploaded_at.isoformat() if f.uploaded_at else None
                result.append({
                    "id": f.id,
                    "filename": f.filename,
                    "file_url": f.file_url,
                    "uploaded_at": uploaded_at,
                    "edited": True,
                })
        return jsonify(result), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error retrieving edited files.",
            "error": str(e)
        }), 500


# ─── 21) Protected dashboard endpoint ──────────────────────────────────────────
@app.route("/api/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    """
    GET /api/dashboard
    Header: Authorization: Bearer <access_token>
    Returns JSON: { msg, role, user }
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({"msg": "User not found"}), 404

        jwt_data = get_jwt()
        role = jwt_data.get("role") or user.role

        if role == "admin":
            welcome_msg = f"Welcome, Admin {user.name}! This is your admin dashboard."
        else:
            welcome_msg = f"Welcome, {user.name}! This is your user dashboard."

        return jsonify({"msg": welcome_msg, "role": role, "user": user.to_dict()}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "msg": "Internal server error retrieving dashboard.",
            "error": str(e)
        }), 500


# ─── 22) Run the app ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Running in debug mode so you see full stack traces immediately
    app.run(debug=True)
