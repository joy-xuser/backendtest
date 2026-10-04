import json
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Agomoni Sur Backend")

# CORS এনাবল করা যাতে GitHub Pages থেকে অবাধে রিকোয়েস্ট আসে
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TRACKS_FILE = "tracks_db.json"

DEFAULT_TRACKS_STORE = {
    'Mahalaya': [
        {
            'id': 'default_m1',
            'title': "মহিষাসুরমর্দিনী (Mahisasuramardini)",
            'artist': "বীরেন্দ্রকৃষ্ণ ভদ্র",
            'duration': "Live",
            'isYoutube': True,
            'ytId': "YQyo8QeoYhc",
            'ytUrl': "https://www.youtube.com/watch?v=YQyo8QeoYhc",
            'image': "https://images.unsplash.com/photo-1534447677768-be436bb09401?q=80&w=300&auto=format&fit=crop"
        }
    ],
    'Shasthi': [
        {
            'id': 'default_s1',
            'title': "Dhak Solo & Agomoni Dhun",
            'artist': "Traditional Dhak Beats",
            'duration': "Live",
            'isYoutube': False,
            'url': "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            'image': "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=300&auto=format&fit=crop&q=80"
        }
    ],
    'Saptami': [],
    'Ashtami': [],
    'Navami': [],
    'Dashami': []
}

def load_tracks_from_disk():
    if os.path.exists(TRACKS_FILE):
        try:
            with open(TRACKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_TRACKS_STORE.copy()

def save_tracks_to_disk(data):
    try:
        with open(TRACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Disk Save Error]: {e}")

@app.get("/")
def home():
    return {"status": "running", "service": "Agomoni Audio Backend"}

@app.get("/ping")
def ping():
    return {"status": "pong", "active": True}

# সব ডিভাইস থেকে সেন্ট্রাল প্লেলিস্ট ফেচ করার জন্য (এটি 404 ফিক্স করবে)
@app.get("/api/tracks")
def get_shared_tracks():
    return load_tracks_from_disk()

# যেকোনো ডিভাইস থেকে প্লেলিস্টে গান সেভ করার জন্য
@app.post("/api/tracks")
async def save_shared_tracks(request: Request):
    try:
        body = await request.json()
        current_data = load_tracks_from_disk()
        
        category = body.get("category")
        new_tracks = body.get("tracks", [])
        
        if category and isinstance(new_tracks, list):
            if category not in current_data:
                current_data[category] = []
            current_data[category].extend(new_tracks)
            save_tracks_to_disk(current_data)
            return {"success": True, "count": len(current_data[category])}
            
        if "playlists" in body:
            current_data = body["playlists"]
            save_tracks_to_disk(current_data)
            return {"success": True}
            
        return {"success": False, "message": "Invalid payload"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# পুরো YouTube Playlist ফেচ করার এন্ডপয়েন্ট
@app.get("/playlist")
def get_playlist(url: str):
    playlist_opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True
    }
    try:
        with yt_dlp.YoutubeDL(playlist_opts) as ydl:
            data = ydl.extract_info(url, download=False)
            entries = data.get("entries", [])
            tracks = []
            for item in entries:
                if not item:
                    continue
                video_id = item.get("id")
                if video_id:
                    tracks.append({
                        "id": f"yt_{video_id}",
                        "title": item.get("title", "Unknown Title"),
                        "artist": item.get("uploader", item.get("channel", "Unknown Artist")),
                        "duration": "Live",
                        "isYoutube": True,
                        "ytId": video_id,
                        "ytUrl": f"https://www.youtube.com/watch?v={video_id}",
                        "image": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    })

            if not tracks:
                raise HTTPException(status_code=404, detail="No tracks found")

            return {"tracks": tracks, "count": len(tracks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
