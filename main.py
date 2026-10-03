import subprocess
import json
import urllib.parse
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import httpx

app = FastAPI(title="Ad-Free YT Audio Engine")

# CORS এনাবল করা যাতে GitHub Pages থেকে কোনো বাধা ছাড়াই কল করা যায়
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"status": "running", "engine": "FastAPI + yt-dlp"}

# স্লিপ প্রিভেনশনের জন্য হেলথ চেক এন্ডপয়েন্ট (Cron-job এখানে হিট করবে)
@app.get("/ping")
def ping():
    return {"status": "pong", "active": True}

# মেটাডাটা পাওয়ার এন্ডপয়েন্ট (টাইটেল, শিল্পী, থাম্বনেইল)
@app.get("/info")
def get_info(url: str):
    try:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-playlist",
            "--no-warnings",
            url
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if proc.returncode != 0:
            raise HTTPException(status_code=400, detail="Video extraction failed")
        
        data = json.loads(proc.stdout)
        return {
            "title": data.get("title", "Unknown Title"),
            "artist": data.get("uploader", data.get("channel", "Unknown Artist")),
            "duration": data.get("duration", 0),
            "thumbnail": data.get("thumbnail", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# বিজ্ঞাপন ছাড়া ডিরেক্ট অডিও স্ট্রিম করার মূল এন্ডপয়েন্ট
@app.get("/stream")
async def stream_audio(url: str):
    try:
        # yt-dlp দিয়ে শুধু সেরা অডিও স্ট্রিম লিংক বের করা
        cmd = [
            "yt-dlp",
            "-f", "bestaudio[ext=m4a]/bestaudio/best",
            "-g",
            "--no-playlist",
            url
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if proc.returncode != 0:
            raise HTTPException(status_code=400, detail="Failed to fetch direct audio stream")
        
        direct_stream_url = proc.stdout.strip()
        if not direct_stream_url:
            raise HTTPException(status_code=404, detail="Stream URL not found")

        # ব্যাকএন্ড থেকে সরাসরি অডিও স্ট্রিম পাইপ করা (No Ads, Pure Audio)
        client = httpx.AsyncClient(timeout=60.0)
        req = client.build_request("GET", direct_stream_url)
        res = await client.send(req, stream=True)

        async def audio_generator():
            try:
                async for chunk in res.aiter_bytes(chunk_size=1024 * 64):
                    yield chunk
            finally:
                await res.aclose()
                await client.aclose()

        headers = {
            "Content-Type": res.headers.get("content-type", "audio/mp4"),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600"
        }
        if "content-length" in res.headers:
            headers["Content-Length"] = res.headers["content-length"]

        return StreamingResponse(audio_generator(), headers=headers)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)