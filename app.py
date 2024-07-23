from flask import Flask, request, jsonify, render_template, send_from_directory
import yt_dlp
import os
import threading
from flask_socketio import SocketIO, emit
import re
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
video_cache = {}
download_progress = {}
playlist_videos = []

@app.route('/')
def index():
    return "Welcome to the YouTube Playlist Viewer!"

@app.route('/playlist/<playlist_id>')
def get_playlist(playlist_id):
    global playlist_videos
    playlist_videos = fetch_playlist_videos(playlist_id)
    print("Fetched playlist videos:", playlist_videos)  # Debugging line
    return render_template('thumbnails.html', playlist_videos=playlist_videos)

@app.route('/video/<filename>')
def serve_video(filename):
    return send_from_directory('cache', filename)

def fetch_playlist_videos(playlist_id):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(f'https://www.youtube.com/playlist?list={playlist_id}', download=False)
    
    videos = []
    for entry in info_dict.get('entries', []):
        video_id = entry.get('id', 'unknown')
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        video_title = entry.get('title', 'No title')
        video_thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        
        video = {
            'id': video_id,
            'thumbnail': video_thumbnail,
            'title': video_title,
            'url': video_url
        }
        videos.append(video)
    
    return videos

def download_video(video_url, video_id):
    def progress_hook(d):
        if d['status'] == 'downloading':
            progress = d['_percent_str']
            # Remove ANSI escape codes
            progress = re.sub(r'\x1b\[([0-9;]*[mG])', '', progress)
            socketio.emit('progress', {'video_id': video_id, 'progress': progress})
        elif d['status'] == 'finished':
            socketio.emit('progress', {'video_id': video_id, 'progress': '100%'})

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'./cache/{video_id}.%(ext)s',
        'progress_hooks': [progress_hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

@app.route('/download_video', methods=['POST'])
def download_video_endpoint():
    data = request.json
    video_url = data.get('video_url')
    video_id = data.get('video_id')

    if not video_url or not video_id:
        return jsonify({"status": "error", "message": "Missing video_url or video_id"}), 400
    
    thread = threading.Thread(target=download_video, args=(video_url, video_id))
    thread.start()
    
    print(f"Download started for video_id: {video_id}, video_url: {video_url}")
    return jsonify({"status": "started"})

@app.route('/delete_video/<video_id>')
def delete_video(video_id):
    for filename in os.listdir('./cache'):
        if filename.startswith(video_id):
            os.remove(f'./cache/{filename}')
            video_cache.pop(f'./cache/{filename}', None)
            download_progress.pop(f'./cache/{filename}', None)
            break
    print(f"Deleted video with id: {video_id}")
    return jsonify({"status": "deleted"})

if __name__ == '__main__':
    if not os.path.exists('./cache'):
        os.makedirs('./cache')
    socketio.run(app, debug=True)
