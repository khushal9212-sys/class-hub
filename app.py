from flask import Flask, render_template, request, redirect, url_for, session, abort
from supabase import create_client
from functools import wraps
import uuid
import hashlib
from datetime import datetime, date, timedelta
import re

app = Flask(__name__)
app.secret_key = "randomtext"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

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

# ===== SIMPLE ADMIN CHECK (NO DECORATOR) =====
def is_admin():
    """Simple check if user is admin"""
    return session.get('is_admin', False)

# ===== HELPER FUNCTION TO DELETE FROM STORAGE =====
def delete_from_storage(file_url):
    if not file_url:
        return False
    try:
        if "class-files" in file_url:
            parts = file_url.split("class-files/")
            if len(parts) > 1:
                storage_path = parts[1].split("?")[0]
                print(f"🗑️ Deleting from storage: {storage_path}")
                supabase.storage.from_(BUCKET).remove([storage_path])
                return True
        return False
    except Exception as e:
        print(f"❌ Storage deletion error: {e}")
        return False

# ===== HOME ROUTE =====
@app.route("/")
def home():
    streams = supabase.table("streams").select("*").execute().data
    stream_map = {s["id"]: s["name"] for s in streams}

    announcements = supabase.table("announcements").select("*").order("created_at", desc=True).limit(1).execute().data
    latest_announcement = announcements[0] if announcements else None

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
                         past_dates=past_dates,
                         admin=is_admin())

# ===== DATE ROUTES =====
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

# ===== SUBJECT ROUTES =====
@app.route("/subject/<int:stream_id>")
def subject(stream_id):
    stream = supabase.table("streams").select("*").eq("id", stream_id).execute().data[0]
    folders = {ft: supabase.table("files").select("*").eq("stream_id", stream_id).eq("folder_type", ft).order("uploaded_at", desc=True).execute().data for ft in FOLDER_TYPES}
    return render_template("subject.html", stream=stream, folders=folders, folder_types=FOLDER_TYPES, folder_labels=FOLDER_LABELS, admin=is_admin())

@app.route("/subject/<int:stream_id>/upload/<folder_type>", methods=["POST"])
def upload_file(stream_id, folder_type):
    file = request.files["file"]
    uploader_name = request.form.get("uploader_name", "")
    file_bytes = file.read()
    file_hash = hashlib.md5(file_bytes).hexdigest()
    original_filename = file.filename

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

# ===== GENERAL DOCUMENTS ROUTES =====
@app.route("/general")
def general_docs():
    files = supabase.table("files").select("*").is_("stream_id", "null").order("uploaded_at", desc=True).execute().data
    return render_template("general.html", files=files, admin=is_admin())

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

# ===== ANNOUNCEMENT ROUTES =====
@app.route("/announcements")
def announcements():
    posts = supabase.table("announcements").select("*").order("created_at", desc=True).execute().data
    streams = supabase.table("streams").select("*").execute().data
    stream_map = {s["id"]: s["name"] for s in streams}
    for p in posts:
        p["stream_name"] = stream_map.get(p.get("stream_id"))
    return render_template("announcements.html", posts=posts, streams=streams, admin=is_admin())

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

# ===== POLL ROUTES =====
@app.route("/polls")
def polls():
    poll_list = supabase.table("polls").select("*").order("created_at", desc=True).execute().data
    
    for poll in poll_list:
        poll["options"] = supabase.table("poll_options").select("*").eq("poll_id", poll["id"]).execute().data
        poll["total_votes"] = sum(opt.get("vote_count", 0) for opt in poll["options"])
    
    return render_template("polls.html", polls=poll_list, admin=is_admin())

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

# ===== ADMIN ROUTES =====
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") != ADMIN_PASSWORD:
            return render_template("admin_login.html", error="Wrong password")
        
        # Set admin session
        session['is_admin'] = True
        session.permanent = True
        
        # Debug: Print session to logs
        print(f"🔐 Admin logged in. Session: {dict(session)}")
        
        return render_template("admin.html",
            files=supabase.table("files").select("*").order("uploaded_at", desc=True).limit(20).execute().data,
            announcements=supabase.table("announcements").select("*").order("created_at", desc=True).limit(10).execute().data,
            polls=supabase.table("polls").select("*").order("created_at", desc=True).limit(10).execute().data,
            admin=True)
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for('home'))

# ===== ADMIN DELETE ROUTES - WITH MANUAL ADMIN CHECK =====

@app.route("/admin/delete/file/<int:file_id>", methods=["POST"])
def admin_delete_file(file_id):
    # MANUAL ADMIN CHECK (no decorator)
    if not session.get('is_admin'):
        print("❌ Not admin, redirecting to login")
        return redirect(url_for('admin'))
    
    print(f"✅ Admin confirmed. Deleting file {file_id}")
    
    try:
        file_data = supabase.table("files").select("*").eq("id", file_id).execute().data
        if not file_data:
            return "File not found", 404
        
        file = file_data[0]
        filename = file.get('filename', 'Unknown')
        file_url = file.get('file_url', '')
        
        print(f"🗑️ Deleting file: {filename}")
        
        # Delete from storage
        delete_from_storage(file_url)
        
        # Delete from database
        supabase.table("files").delete().eq("id", file_id).execute()
        print(f"✅ File deleted: {filename}")
        
        return redirect(request.referrer or url_for("admin"))
    
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(request.referrer or url_for("admin"))

@app.route("/admin/delete/announcement/<int:announcement_id>", methods=["POST"])
def admin_delete_announcement(announcement_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        announcement = supabase.table("announcements").select("*").eq("id", announcement_id).execute().data
        if announcement:
            file_url = announcement[0].get("file_url")
            if file_url:
                delete_from_storage(file_url)
        
        supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return redirect(request.referrer or url_for("announcements"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(request.referrer or url_for("admin"))

@app.route("/admin/delete/poll/<int:poll_id>", methods=["POST"])
def admin_delete_poll(poll_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        supabase.table("poll_options").delete().eq("poll_id", poll_id).execute()
        supabase.table("polls").delete().eq("id", poll_id).execute()
        return redirect(request.referrer or url_for("polls"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(request.referrer or url_for("admin"))

@app.route("/admin/delete/date/<int:date_id>", methods=["POST"])
def admin_delete_date(date_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        date_data = supabase.table("important_dates").select("*").eq("id", date_id).execute().data
        if date_data:
            file_url = date_data[0].get("file_url")
            if file_url:
                delete_from_storage(file_url)
        
        attachments = supabase.table("date_attachments").select("*").eq("date_id", date_id).execute().data
        for att in attachments:
            if att.get("file_url"):
                delete_from_storage(att["file_url"])
        
        supabase.table("date_attachments").delete().eq("date_id", date_id).execute()
        supabase.table("important_dates").delete().eq("id", date_id).execute()
        return redirect(request.referrer or url_for("home"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(request.referrer or url_for("admin"))

@app.route("/admin/delete/attachment/<int:attachment_id>", methods=["POST"])
def admin_delete_attachment(attachment_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        attachment = supabase.table("date_attachments").select("*").eq("id", attachment_id).execute().data
        if attachment and attachment[0].get("file_url"):
            delete_from_storage(attachment[0]["file_url"])
        
        supabase.table("date_attachments").delete().eq("id", attachment_id).execute()
        return redirect(request.referrer or url_for("home"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(request.referrer or url_for("admin"))

# ===== BULK DELETE =====

@app.route("/admin/delete/all/files", methods=["POST"])
def admin_delete_all_files():
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        files = supabase.table("files").select("*").execute().data
        for file in files:
            file_url = file.get("file_url")
            if file_url:
                delete_from_storage(file_url)
        supabase.table("files").delete().neq("id", 0).execute()
        return redirect(url_for("admin"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(url_for("admin"))

@app.route("/admin/delete/all/polls", methods=["POST"])
def admin_delete_all_polls():
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        polls = supabase.table("polls").select("*").execute().data
        for poll in polls:
            supabase.table("poll_options").delete().eq("poll_id", poll["id"]).execute()
        supabase.table("polls").delete().neq("id", 0).execute()
        return redirect(url_for("admin"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(url_for("admin"))

@app.route("/admin/delete/all/announcements", methods=["POST"])
def admin_delete_all_announcements():
    if not session.get('is_admin'):
        return redirect(url_for('admin'))
    
    try:
        announcements = supabase.table("announcements").select("*").execute().data
        for announcement in announcements:
            file_url = announcement.get("file_url")
            if file_url:
                delete_from_storage(file_url)
        supabase.table("announcements").delete().neq("id", 0).execute()
        return redirect(url_for("admin"))
    except Exception as e:
        print(f"❌ Delete error: {e}")
        return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)