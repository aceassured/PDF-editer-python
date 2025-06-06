# PDF Editor Python

A full-stack web application that allows users to upload, view, and annotate PDF files. Built with a Python/Flask backend and a React frontend, this project supports role-based access: “user” accounts can upload and edit PDFs, and “admin” accounts can review and manage all uploaded and edited files.

---

## Table of Contents

* [Features](#features)
* [Tech Stack](#tech-stack)
* [Project Structure](#project-structure)
* [Getting Started](#getting-started)

  * [Prerequisites](#prerequisites)
  * [Backend Setup](#backend-setup)
  * [Frontend Setup](#frontend-setup)
* [Environment Variables](#environment-variables)
* [Usage](#usage)
* [License](#license)

---

## Features

* **User Registration & Login**
  Secure authentication with role-based access (“user” or “admin”).

* **PDF Upload & Storage**
  Users can upload PDF files; files are stored via Vercel Blob (or locally as a fallback).

* **In-Browser PDF Editing**
  Drag-and-drop text annotations directly onto the PDF pages; resized and repositioned as needed.

* **Admin Dashboard**
  Admins can:

  * View a list of all uploaded files (with uploader ID and name)
  * View a list of all edited files (with editor ID and name)
  * Preview any PDF or its edited version

* **RESTful API**
  Flask-powered backend exposing endpoints for authentication, file upload, file retrieval, and editing.

* **Clean UI**
  React + Vite frontend with responsive layout, form validation, and interactive PDF editing.

---

## Tech Stack

* **Backend**

  * Python 3.9+
  * Flask
  * Flask-SQLAlchemy (PostgreSQL)
  * Flask-JWT-Extended
  * Flask-CORS
  * PDF-Lib (for server-side PDF manipulation)

* **Frontend**

  * React 18+ (with Vite)
  * Axios
  * react-pdf
  * react-rnd (draggable/resizable text boxes)
  * TailwindCSS (optional utilities)

* **Database**

  * PostgreSQL (or SQLite for local dev)

* **Storage**

  * Vercel Blob for PDF and edited file hosting

---

## Project Structure

```
pdf-editor-python/
├── backend/
│   ├── app.py
│   ├── models.py
│   ├── requirements.txt
│   └── ...  
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── context/
│   │   ├── pages/
│   │   ├── index.css
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── .gitignore
└── README.md
```

* **backend/**

  * `app.py`: Main Flask application, defines routes and CORS.
  * `models.py`: SQLAlchemy models for Users and Files.
  * `requirements.txt`: Python dependencies.

* **frontend/**

  * `src/api/api.js`: Axios instance configured with base URL and JWT interceptors.
  * `src/context/AuthContext.jsx`: Provides auth state (`user`, `login()`, `logout()`).
  * `src/pages/`:

    * `Login.jsx`, `Register.jsx`
    * `Dashboard.jsx` (user vs. admin view)
    * `Upload.jsx` (file upload form)
    * `CanvaStyleEdit.jsx` (drag-and-drop PDF editor)
  * `src/index.css`: Global styles for cards, buttons, forms, etc.
  * `vite.config.js`: Vite configuration.

---

## Getting Started

### Prerequisites

* **Node.js** ≥ 16
* **npm** (comes with Node.js)
* **Python** ≥ 3.9
* **pipenv** or **venv** (for Python virtual environments)
* **PostgreSQL** (or SQLite for local development)

---

### Backend Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/pdf-editor-python.git
   cd pdf-editor-python/backend
   ```

2. **Create & activate a virtual environment**

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install Python dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a file named `.env` in `backend/` with the following contents:

   ```
   FLASK_APP=app.py
   FLASK_ENV=development
   DATABASE_URL=postgresql://<username>:<password>@localhost:5432/<your_db_name>
   JWT_SECRET_KEY=your_jwt_secret
   VERCEL_BLOB_UPLOAD_URL=https://<your-vercel-blob-endpoint>/
   VERCEL_BLOB_TOKEN=your_vercel_blob_token
   ```

   * If you prefer SQLite locally, set `DATABASE_URL=sqlite:///db.sqlite3`.

5. **Initialize the database**
   Make sure your Postgres server is running. Then, in `backend/`:

   ```bash
   flask db init
   flask db migrate
   flask db upgrade
   ```

6. **Run the Flask server**

   ```bash
   flask run
   ```

   The backend will start at `http://127.0.0.1:5000`.

---

### Frontend Setup

1. **Open a new terminal & navigate to frontend/**

   ```bash
   cd ../frontend
   ```

2. **Install npm dependencies**

   ```bash
   npm install
   ```

3. **Start the development server**

   ```bash
   npm run dev
   ```

   The React app will be available at `http://localhost:5173`.

---

## Environment Variables

### Backend (`backend/.env`)

```env
FLASK_APP=app.py
FLASK_ENV=development
DATABASE_URL=postgresql://<DB_USER>:<DB_PASS>@localhost:5432/<DB_NAME>
JWT_SECRET_KEY=your_jwt_secret_key
VERCEL_BLOB_UPLOAD_URL=https://<vercel-blob-endpoint>/
VERCEL_BLOB_TOKEN=vercel_blob_token_here
```

### Frontend

No additional environment variables are required if the frontend uses relative `http://localhost:5000/api` routes. If deployed, you may add a `.env` in `frontend/` with:

```env
VITE_API_BASE_URL=https://your-production-backend.com/api
```

And update `src/api/api.js` to use `import.meta.env.VITE_API_BASE_URL` instead of hardcoding `/api`.

---

## Usage

1. **Register** a new user via `http://localhost:5173/register`.
2. **Log in** as that user.
3. **Upload** a PDF by navigating to “Upload a New PDF” on the user dashboard.
4. **Edit** the uploaded PDF in-browser by dragging text boxes and saving.
5. **Switch to Admin** (log out, then log in with an `admin` account) to review all uploaded and edited files.

---

Enjoy building and customizing “PDF Editor Python”!
