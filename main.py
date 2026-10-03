import urllib.parse
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import yt_dlp

app = FastAPI(title="Ad-Free YT Audio Engine")

# CORS এনাবল করা যাতে GitHub Pages থেকে কোনো বাধা ছাড়াই কল করা যায়
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# yt-dlp এর জন্য শক্তিশালী কনফিগারেশন (Android Client দিয়ে ডেটাসেন্টার আইপি ব্লক বাইপাস)
YDL_AUDIO_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "extract_flat": False,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"]
        }
    }
}

@app.get("/")
def home():
    return {"status": "running", "engine": "FastAPI + yt-dlp (Native)"}

# স্লিপ প্রিভেনশনের জন্য হেলথ চেক
@app.get("/ping")
def ping():
    return {"status": "pong", "active": True}

# একক গানের মেটাডাটা পাওয়ার এন্ডপয়েন্ট
@app.get("/info")
def get_info(url: str):
    try:
        with yt_dlp.YoutubeDL(YDL_AUDIO_OPTS) as ydl:
            data = ydl.extract_info(url, download=False)
            return {
                "title": data.get("title", "Unknown Title"),
                "artist": data.get("uploader", data.get("channel", "Unknown Artist")),
                "duration": data.get("duration", 0),
                "thumbnail": data.get("thumbnail", "")
            }
    except Exception as e:
        print(f"Info extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# সম্পূর্ণ YouTube প্লেলিস্ট ফেচ করার এন্ডপয়েন্ট
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
                raise HTTPException(status_code=404, detail="No tracks found in playlist")

            return {"tracks": tracks, "count": len(tracks)}
    except Exception as e:
        print(f"Playlist extraction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# বিজ্ঞাপন ছাড়া ডিরেক্ট অডিও স্ট্রিম করার মূল এন্ডপয়েন্ট (হেডার ম্যাচিংসহ)
@app.get("/stream")
async def stream_audio(url: str, request: Request):
    try:
        with yt_dlp.YoutubeDL(YDL_AUDIO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # সরাসরি অডিও স্ট্রিম URL এবং প্রয়োজনীয় হেডার সংগ্রহ
            stream_url = info.get("url")
            stream_headers = info.get("http_headers", {})

        if not stream_url:
            raise HTTPException(status_code=404, detail="Stream URL not found")

        # ব্রাউজারের রেঞ্জ রিকোয়েস্ট পাস করা যাতে অডিও স্কিপ/সিকিং কাজ করে
        client_range = request.headers.get("range")
        if client_range:
            stream_headers["Range"] = client_range

        client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
        req = client.build_request("GET", stream_url, headers=stream_headers)
        res = await client.send(req, stream=True)

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
        print(f"Stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
