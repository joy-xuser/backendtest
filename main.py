import urllib.parse
import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import yt_dlp

app = FastAPI(title="Ad-Free YT Audio Engine")

# CORS এনাবল করা যাতে GitHub Pages থেকে নির্বিঘ্নে কল করা যায়
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# শক্তিশালী yt-dlp কনফিগারেশন: iOS/Android ক্লায়েন্ট দিয়ে বটগার্ড ও PoToken বাইপাস
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
    "extractor_args": {
        "youtube": {
            "player_client": ["ios", "android", "mweb"]
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
    }
}

@app.get("/")
def home():
    return {"status": "running", "engine": "FastAPI + yt-dlp Auto-Recovery"}

@app.get("/ping")
def ping():
    return {"status": "pong", "active": True}

def extract_stream_url(info: dict):
    """ব্রাউজারে শতভাগ চলার মতো m4a বা সেরা অডিও ফরম্যাট বাছাই করা"""
    if not info:
        return None, {}

    # সরাসরি url থাকলে
    if info.get("url"):
        return info["url"], info.get("http_headers", {})

    formats = info.get("formats", [])
    if not formats:
        return None, {}

    # অডিও ফরম্যাট ফিল্টার (m4a/mp4 ব্রাউজারে সবচেয়ে ভালো সাপোর্ট করে)
    audio_formats = [
        f for f in formats 
        if f.get("url") and f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
    ]
    
    # প্রথম পছন্দ: m4a (আইওএস, অ্যান্ড্রয়েড, পিসি সব ব্রাউজারে সাথে সাথে বাজে)
    m4a_formats = [f for f in audio_formats if f.get("ext") == "m4a"]
    if m4a_formats:
        m4a_formats.sort(key=lambda x: x.get("abr") or 0, reverse=True)
        chosen = m4a_formats[0]
        return chosen["url"], chosen.get("http_headers", {})

    if audio_formats:
        audio_formats.sort(key=lambda x: x.get("abr") or 0, reverse=True)
        chosen = audio_formats[0]
        return chosen["url"], chosen.get("http_headers", {})

    # শেষ বিকল্প
    for f in reversed(formats):
        if f.get("url"):
            return f["url"], f.get("http_headers", {})

    return None, {}

@app.get("/info")
def get_info(url: str):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)
            return {
                "title": data.get("title", "Unknown Title"),
                "artist": data.get("uploader", data.get("channel", "Unknown Artist")),
                "duration": data.get("duration", 0),
                "thumbnail": data.get("thumbnail", "")
            }
    except Exception as e:
        print(f"[Info Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
                        "duration": "Stream",
                        "isYoutube": True,
                        "ytUrl": f"https://www.youtube.com/watch?v={video_id}",
                        "url": None,
                        "image": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                    })

            if not tracks:
                raise HTTPException(status_code=404, detail="No tracks found")

            return {"tracks": tracks, "count": len(tracks)}
    except Exception as e:
        print(f"[Playlist Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# পিওর বিজ্ঞাপনবিহীন অডিও স্ট্রিমিং (হেডার ফরোয়ার্ডিং ও রেঞ্জ কন্ট্রোলসহ)
@app.get("/stream")
async def stream_audio(url: str, request: Request):
    stream_url = None
    stream_headers = {}

    # ১. yt-dlp দিয়ে স্ট্রিম খোঁজা
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            stream_url, stream_headers = extract_stream_url(info)
    except Exception as e:
        print(f"[yt-dlp extract error]: {e}")

    # ২. ফলব্যাক: Piped API থেকে অডিও স্ট্রিম বের করা
    if not stream_url:
        video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
        if video_id_match:
            vid = video_id_match.group(1)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    piped_res = await client.get(f"https://pipedapi.kavin.rocks/streams/{vid}")
                    if piped_res.status_code == 200:
                        piped_data = piped_res.json()
                        audio_streams = piped_data.get("audioStreams", [])
                        if audio_streams:
                            stream_url = audio_streams[0].get("url")
            except Exception as pe:
                print(f"[Piped fallback error]: {pe}")

    if not stream_url:
        raise HTTPException(status_code=404, detail="Audio stream unavailable")

    # ব্রাউজারের রেঞ্জ রিকোয়েস্ট পাস করা যাতে অডিও স্কিপ/সিকিং মসৃণভাবে চলে
    req_headers = dict(stream_headers) if stream_headers else {}
    client_range = request.headers.get("range")
    if client_range:
        req_headers["Range"] = client_range

    if "User-Agent" not in req_headers:
        req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    try:
        client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
        upstream_req = client.build_request("GET", stream_url, headers=req_headers)
        res = await client.send(upstream_req, stream=True)

        async def audio_generator():
            try:
                async for chunk in res.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk
            finally:
                await res.aclose()
                await client.aclose()

        response_headers = {
            "Content-Type": res.headers.get("content-type", "audio/mp4"),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600"
        }
        if "content-length" in res.headers:
            response_headers["Content-Length"] = res.headers["content-length"]
        if "content-range" in res.headers:
            response_headers["Content-Range"] = res.headers["content-range"]

        return StreamingResponse(
            audio_generator(), 
            status_code=res.status_code, 
            headers=response_headers
        )

    except Exception as e:
        print(f"[Streaming Pipe Error]: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
