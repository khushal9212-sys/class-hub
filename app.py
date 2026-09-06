from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client
import uuid
import hashlib
import os
from datetime import datetime, date, timedelta
import pytz

app = Flask(__name__)
app.secret_key = "randomtext"  # Change to environment variable in production

SUPABASE_URL = "https://kjasslioidmuxnwctdyg.supabase.co"
SUPABASE_KEY = "sb_publishable__BzdVERihynzsfzuL6SVHw_7njcjjr6"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "class-files"
ADMIN_PASSWORD = "khushal9212"

FOLDER_TYPES = ["general", "notes", "syllabus", "question_paper", "answer"]
FOLDER_LABELS = {
    "general": "General", "notes": "Notes", "syllabus": "Syllabus",
    "question_paper": "Question Papers", "answer": "Answers"
}

@app.route("/")
def home():
    streams = supabase.table("streams").select("*").execute().data
    stream_map = {s["id"]: s["name"] for s in streams}

    announcements = supabase.table("announcements").select("*").order("created_at", desc=True).limit(1).execute().data
    latest_announcement = announcements[0] if announcements else None

    # Get ALL dates
    all_dates = supabase.table("important_dates").select("*").order("date").execute().data
    
    today = date.today()
    future_dates = []
    past_dates = []
    
    for d in all_dates:
        date_obj = datetime.strptime(d["date"], "%Y-%m-%d").date()
        d["stream_name"] = stream_map.get(d.get("stream_id"))
        d["attachments"] = supabase.table("date_attachments").select("*").eq("date_id", d["id"]).order("uploaded_at", desc=True).execute().data
        
        if date_obj >= today:
            future_dates.append(d)
        else:
            past_dates.append(d)

    return render_template("home.html", 
                         streams=streams, 
                         latest_announcement=latest_announcement, 
                         future_dates=future_dates,
                         past_dates=past_dates)

@app.route("/dates/add", methods=["POST"])
def add_date():
    stream_id = request.form.get("stream_id")
    file = request.files.get("file")
    file_url = None
    if file and file.filename:
        ext = file.filename.split(".")[-1]
        path = f"dates/{uuid.uuid4()}.{ext}"
        supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.content_type})
        file_url = supabase.storage.from_(BUCKET).get_public_url(path)

    supabase.table("important_dates").insert({
        "title": request.form.get("title"),
        "date": request.form.get("date"),
        "type": request.form.get("type"),
        "stream_id": int(stream_id) if stream_id else None,
        "description": request.form.get("description"),
        "file_url": file_url
    }).execute()
    return redirect(url_for("home"))

@app.route("/subject/<int:stream_id>")
def subject(stream_id):
    stream = supabase.table("streams").select("*").eq("id", stream_id).execute().data[0]
    folders = {ft: supabase.table("files").select("*").eq("stream_id", stream_id).eq("folder_type", ft).order("uploaded_at", desc=True).execute().data for ft in FOLDER_TYPES}
    return render_template("subject.html", stream=stream, folders=folders, folder_types=FOLDER_TYPES, folder_labels=FOLDER_LABELS)

@app.route("/subject/<int:stream_id>/upload/<folder_type>", methods=["POST"])
def upload_file(stream_id, folder_type):
    file = request.files["file"]
    uploader_name = request.form.get("uploader_name", "")
    file_bytes = file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    original_filename = file.filename

    # Check for duplicate by hash
    existing = supabase.table("files").select("*").eq("stream_id", stream_id).eq("folder_type", folder_type).eq("file_hash", file_hash).execute().data
    
    if existing:
        return redirect(url_for("subject", stream_id=stream_id, duplicate=1))

    ext = original_filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{ext}"
    path = f"{stream_id}/{folder_type}/{unique_name}"
    supabase.storage.from_(BUCKET).upload(path, file_bytes, {"content-type": file.content_type})
    file_url = supabase.storage.from_(BUCKET).get_public_url(path)

    supabase.table("files").insert({
        "stream_id": stream_id, "folder_type": folder_type, "uploader_name": uploader_name,
        "filename": original_filename, "file_url": file_url, "file_hash": file_hash
    }).execute()
    return redirect(url_for("subject", stream_id=stream_id))

@app.route("/general")
def general_docs():
    files = supabase.table("files").select("*").is_("stream_id", "null").order("uploaded_at", desc=True).execute().data
    return render_template("general.html", files=files)

@app.route("/general/upload", methods=["POST"])
def upload_general():
    file = request.files["file"]
    uploader_name = request.form.get("uploader_name", "")
    file_bytes = file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    original_filename = file.filename

    existing = supabase.table("files").select("*").is_("stream_id", "null").eq("file_hash", file_hash).execute().data
    if existing:
        return redirect(url_for("general_docs", duplicate=1))

    ext = original_filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{ext}"
    path = f"general-docs/{unique_name}"
    supabase.storage.from_(BUCKET).upload(path, file_bytes, {"content-type": file.content_type})
    file_url = supabase.storage.from_(BUCKET).get_public_url(path)

    supabase.table("files").insert({
        "stream_id": None, "folder_type": "general", "uploader_name": uploader_name,
        "filename": original_filename, "file_url": file_url, "file_hash": file_hash
    }).execute()
    return redirect(url_for("general_docs"))

@app.route("/announcements")
def announcements():
    posts = supabase.table("announcements").select("*").order("created_at", desc=True).execute().data
    streams = supabase.table("streams").select("*").execute().data
    stream_map = {s["id"]: s["name"] for s in streams}
    for p in posts:
        p["stream_name"] = stream_map.get(p.get("stream_id"))
    return render_template("announcements.html", posts=posts, streams=streams)

@app.route("/announcements/post", methods=["POST"])
def post_announcement():
    stream_id = request.form.get("stream_id")
    file = request.files.get("file")
    file_url = None
    if file and file.filename:
        ext = file.filename.split(".")[-1]
        path = f"announcements/{uuid.uuid4()}.{ext}"
        supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.content_type})
        file_url = supabase.storage.from_(BUCKET).get_public_url(path)
    supabase.table("announcements").insert({
        "text": request.form.get("text"), "uploader_name": request.form.get("uploader_name", ""),
        "file_url": file_url, "stream_id": int(stream_id) if stream_id else None
    }).execute()
    return redirect(url_for("announcements"))

@app.route("/polls")
def polls():
    # Set timezone (adjust to your timezone)
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)
    
    # Get ALL polls (both active and closed)
    poll_list = supabase.table("polls").select("*").order("created_at", desc=True).execute().data
    
    for poll in poll_list:
        # Auto-close polls older than 7 days
        if poll["is_active"]:
            created_at = datetime.fromisoformat(poll["created_at"].replace('Z', '+00:00'))
            age = now - created_at
            if age.days >= 7:
                supabase.table("polls").update({"is_active": False}).eq("id", poll["id"]).execute()
                poll["is_active"] = False
        
        poll["options"] = supabase.table("poll_options").select("*").eq("poll_id", poll["id"]).execute().data
        poll["total_votes"] = sum(opt.get("vote_count", 0) for opt in poll["options"])
    
    return render_template("polls.html", polls=poll_list)

@app.route("/polls/create", methods=["POST"])
def create_poll():
    options = request.form.getlist("options")
    poll = supabase.table("polls").insert({"question": request.form.get("question"), "is_active": True}).execute().data[0]
    for opt in options:
        if opt.strip():
            supabase.table("poll_options").insert({"poll_id": poll["id"], "option_text": opt}).execute()
    return redirect(url_for("polls"))

@app.route("/polls/vote/<int:option_id>", methods=["POST"])
def vote(option_id):
    option = supabase.table("poll_options").select("*").eq("id", option_id).execute().data[0]
    poll_id = option["poll_id"]
    
    # Check if poll is still active
    poll = supabase.table("polls").select("*").eq("id", poll_id).execute().data[0]
    if not poll["is_active"]:
        return redirect(url_for("polls", already_voted=1))
    
    voted = session.get("voted_polls", [])
    if poll_id in voted:
        return redirect(url_for("polls", already_voted=1))
    
    supabase.table("poll_options").update({"vote_count": option["vote_count"] + 1}).eq("id", option_id).execute()
    voted.append(poll_id)
    session["voted_polls"] = voted
    return redirect(url_for("polls"))

@app.route("/polls/close/<int:poll_id>", methods=["POST"])
def close_poll(poll_id):
    supabase.table("polls").update({"is_active": False}).eq("id", poll_id).execute()
    return redirect(url_for("polls"))

@app.route("/dates/<int:date_id>/attach", methods=["POST"])
def attach_to_date(date_id):
    file = request.files["file"]
    uploader_name = request.form.get("uploader_name", "")
    ext = file.filename.split(".")[-1]
    path = f"date-attachments/{uuid.uuid4()}.{ext}"
    supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.content_type})
    file_url = supabase.storage.from_(BUCKET).get_public_url(path)
    supabase.table("date_attachments").insert({
        "date_id": date_id, "uploader_name": uploader_name,
        "filename": file.filename, "file_url": file_url
    }).execute()
    return redirect(url_for("home"))

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") != ADMIN_PASSWORD:
            return render_template("admin_login.html", error="Wrong password")
        return render_template("admin.html",
            files=supabase.table("files").select("*").order("uploaded_at", desc=True).limit(20).execute().data,
            announcements=supabase.table("announcements").select("*").order("created_at", desc=True).limit(10).execute().data,
            polls=supabase.table("polls").select("*").order("created_at", desc=True).limit(10).execute().data)
    return render_template("admin_login.html")

if __name__ == "__main__":
    app.run(debug=True)