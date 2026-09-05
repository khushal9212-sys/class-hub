from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client
import uuid

app = Flask(__name__)

SUPABASE_URL = "https://kjasslioidmuxnwctdyg.supabase.co"
SUPABASE_KEY = "sb_publishable__BzdVERihynzsfzuL6SVHw_7njcjjr6"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BUCKET = "class-files"

@app.route("/")
def home():
    streams = supabase.table("streams").select("*").execute().data
    announcements = supabase.table("announcements").select("*").order("created_at", desc=True).limit(1).execute().data
    latest_announcement = announcements[0] if announcements else None
    dates = supabase.table("important_dates").select("*").order("date").execute().data
    return render_template("home.html", streams=streams, latest_announcement=latest_announcement, dates=dates)

@app.route("/dates/add", methods=["POST"])
def add_date():
    title = request.form.get("title")
    date = request.form.get("date")
    type_ = request.form.get("type")
    stream_id = request.form.get("stream_id")
    stream_id = int(stream_id) if stream_id else None

    supabase.table("important_dates").insert({
        "title": title,
        "date": date,
        "type": type_,
        "stream_id": stream_id
    }).execute()

    return redirect(url_for("home"))

@app.route("/subject/<int:stream_id>")
def subject(stream_id):
    stream = supabase.table("streams").select("*").eq("id", stream_id).execute().data[0]
    general_files = supabase.table("files").select("*").eq("stream_id", stream_id).eq("folder_type", "general").order("uploaded_at", desc=True).execute().data
    notes_files = supabase.table("files").select("*").eq("stream_id", stream_id).eq("folder_type", "notes").order("uploaded_at", desc=True).execute().data
    return render_template("subject.html", stream=stream, general_files=general_files, notes_files=notes_files)

@app.route("/subject/<int:stream_id>/upload/<folder_type>", methods=["POST"])
def upload_file(stream_id, folder_type):
    file = request.files["file"]
    uploader_name = request.form.get("uploader_name", "")

    ext = file.filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{ext}"
    path = f"{stream_id}/{folder_type}/{unique_name}"

    supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.content_type})
    file_url = supabase.storage.from_(BUCKET).get_public_url(path)

    supabase.table("files").insert({
        "stream_id": stream_id,
        "folder_type": folder_type,
        "uploader_name": uploader_name,
        "filename": file.filename,
        "file_url": file_url
    }).execute()

    return redirect(url_for("subject", stream_id=stream_id))

@app.route("/announcements")
def announcements():
    posts = supabase.table("announcements").select("*").order("created_at", desc=True).execute().data
    return render_template("announcements.html", posts=posts)

@app.route("/announcements/post", methods=["POST"])
def post_announcement():
    text = request.form.get("text")
    uploader_name = request.form.get("uploader_name", "")
    file = request.files.get("file")
    file_url = None

    if file and file.filename:
        ext = file.filename.split(".")[-1]
        unique_name = f"{uuid.uuid4()}.{ext}"
        path = f"announcements/{unique_name}"
        supabase.storage.from_(BUCKET).upload(path, file.read(), {"content-type": file.content_type})
        file_url = supabase.storage.from_(BUCKET).get_public_url(path)

    supabase.table("announcements").insert({
        "text": text,
        "uploader_name": uploader_name,
        "file_url": file_url
    }).execute()

    return redirect(url_for("announcements"))

@app.route("/polls")
def polls():
    poll_list = supabase.table("polls").select("*").order("created_at", desc=True).execute().data
    for poll in poll_list:
        poll["options"] = supabase.table("poll_options").select("*").eq("poll_id", poll["id"]).execute().data
    return render_template("polls.html", polls=poll_list)

@app.route("/polls/create", methods=["POST"])
def create_poll():
    question = request.form.get("question")
    options = request.form.getlist("options")

    poll = supabase.table("polls").insert({"question": question}).execute().data[0]
    for opt in options:
        if opt.strip():
            supabase.table("poll_options").insert({"poll_id": poll["id"], "option_text": opt}).execute()

    return redirect(url_for("polls"))

@app.route("/polls/vote/<int:option_id>", methods=["POST"])
def vote(option_id):
    option = supabase.table("poll_options").select("*").eq("id", option_id).execute().data[0]
    supabase.table("poll_options").update({"vote_count": option["vote_count"] + 1}).eq("id", option_id).execute()
    return redirect(url_for("polls"))

if __name__ == "__main__":
    app.run(debug=True)