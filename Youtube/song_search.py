# Youtube/song_search_improved_with_reactions.py
import os
import uuid
import yt_dlp
import requests
import asyncio
import random
from concurrent.futures import ThreadPoolExecutor
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import time
from pyrogram.errors import FloodWait
import random
from pyrogram.raw.functions.messages import SendReaction
from Youtube.config import Config



SEARCH_CACHE = {}       # search_id → results
USER_LOCKS = {}         # user_id → True if busy
executor = ThreadPoolExecutor(max_workers=3)


REACTION_EMOJIS = ["❤️", "🔥", "😍"]

# -------------------------
# AUTO REACTION FUNCTION
# -------------------------
async def auto_react(client, message):
    emoji = random.choice(REACTION_EMOJIS)

    try:
        await client.send_reaction(
            chat_id=message.chat.id,
            message_id=message.id,
            emoji=emoji
        )

    except:
        pass


# -------------------------
# SEARCH HANDLER
# -------------------------
@Client.on_message(filters.command(["song", "find"]))
async def song_search(client, message):

    # instantly react
    await auto_react(client, message)

    if not message.from_user or message.from_user.is_bot:
        return

    # your other song search code continues here...

    query = " ".join(message.command[1:]).strip()
    if not query:
        return await message.reply_text(
            "🎵 **Usage:**\n`/song your song name here`\n`/find  your song name or lyrics here`"
        )

    is_lyrics = message.command[0].lower() == "find"
    shown_text = query if not is_lyrics else f"(lyrics) {query}"

    status = await message.reply_text(f"🔍 **Searching:** `{shown_text}`")

    # Background search
    def do_search(q):
        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "no_warnings": True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"ytsearch8:{q}", download=False)

    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(executor, lambda: do_search(query))
    except Exception as e:
        return await status.edit_text(f"❌ Search failed: `{e}`")

    entries = info.get("entries", [])
    if not entries:
        return await status.edit_text("❌ No results found.")

    search_id = str(uuid.uuid4())[:8]
    results = []
    buttons = []

    for i, e in enumerate(entries, start=1):
        title = f"⚝ {e.get('title', 'YouTube Video')}"
        dur = e.get("duration_string") or e.get("duration") or "N/A"
        url = e.get("url") or e.get("id") or e.get("webpage_url")


        if url and not url.startswith("http"):
            url = "https://www.youtube.com/watch?v=" + url

        results.append({"title": title, "duration": dur, "url": url})

        buttons.append([
            InlineKeyboardButton(
                f"{i}. {title[:40]} ({dur})",
                callback_data=f"dl_{search_id}_{i-1}"
            )
        ])

    SEARCH_CACHE[search_id] = results

    await status.edit_text(
        f"🎧 **Results for:** `{shown_text}`\nTap a button to download.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


def format_duration(duration) -> str:
    """
    Convert duration to mm:ss or hh:mm:ss.
    Handles int, float, or string (sometimes returned by yt-dlp).
    """
    try:
        if duration is None:
            return "??:??"
        # Convert string to int if needed
        if isinstance(duration, str):
            duration = int(float(duration))
        duration = int(duration)
        m, s = divmod(duration, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02}:{s:02}"
        return f"{m}:{s:02}"
    except Exception:
        return "??:??"

# -------------------------
# DOWNLOAD CALLBACK
# -------------------------
@Client.on_message(
    filters.command(["song", "find"]) 
    & ~filters.bot
)
async def song_search(client, message):
    await auto_react(client, message)
    query = " ".join(message.command[1:])
    if not query:
        return await message.reply_text(
            "Please type a song name.\nExample: `/song Tera Fitoor`"
        )

    await message.reply_text(f"🎵 Search results for **{query}**...")

    ydl_opts = {
        "cookies": "./cookies.txt",
        "ffmpeg_location": "/usr/bin/ffmpeg",
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch10:{query}", download=False)
            results = info.get("entries", [])
    except Exception as e:
        return await message.reply_text(f"❌ Error: `{e}`")

    if not results:
        return await message.reply_text("No results found ❌")

    search_id = str(uuid.uuid4())[:8]
    SEARCH_CACHE[search_id] = results

    buttons = []
    text = f"🎧 **Search results for:** `{query}`\n\n"

    for i, song in enumerate(results):
        title = song.get("title", "Unknown Title")
        duration = format_duration(song.get("duration"))
        buttons.append(
            [InlineKeyboardButton(f"{title[:40]} ({duration})",
                                  callback_data=f"dl_{search_id}_{i}")]
        )

    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    



# ----------------------------
#        DOWNLOAD HANDLER
# ----------------------------

@Client.on_callback_query(filters.regex("^dl_"))
async def download_music(client, cq: CallbackQuery):

    # Parse callback
    data = cq.data.split("_", 2)
    if len(data) != 3:
        return await cq.answer("Invalid!", show_alert=True)

    _, search_id, idx_s = data
    idx = int(idx_s)

    res_list = SEARCH_CACHE.get(search_id)
    if not res_list or idx >= len(res_list):
        return await cq.answer("Expired search! Try /song again.", show_alert=True)

    entry = res_list[idx]
    user = cq.from_user.id

    # Lock
    if USER_LOCKS.get(user):
        return await cq.answer("⏳ You already have a download running.", show_alert=True)

    USER_LOCKS[user] = True

    # First message
    try:
        progress_msg = await cq.message.edit_text(
            f"🎧 **Downloading:** {entry['title']}\n0%…"
        )
    except:
        progress_msg = cq.message

    loop = asyncio.get_event_loop()

    # -------------------------------------------------
    #           SOLID, ALWAYS-WORKING PROGRESS BAR
    # -------------------------------------------------
    def bar(percent, size=10):
        filled = int((percent / 100) * size)
        return "❤" * filled + "🤍" * (size - filled)

    last_update = 0

    # -------------- FIXED HOOK -----------------------
    def hook(d):
        nonlocal last_update

        if d["status"] != "downloading":
            return

        downloaded = d.get("downloaded_bytes", 0)
        total = d.get("total_bytes") or d.get("total_bytes_estimate")

        if not total:
            percent = 0
        else:
            percent = (downloaded * 100) / total

        # throttle updates
        now = time.time()
        if now - last_update < 0.3:
            return
        last_update = now

        b = bar(percent)

        try:
            asyncio.run_coroutine_threadsafe(
                progress_msg.edit_text(
                    f"🎧 **Downloading:** {entry['title']}\n\n"
                    f"{b} {percent:.0f}%\n"
                    f"({downloaded/1024/1024:.1f}MB / {total/1024/1024:.1f}MB)"
                ),
                loop
            )
        except:
            pass

    # -------------------------------------------------
    #                DOWNLOAD THREAD
    # -------------------------------------------------
    def do_download(url, outtmpl):
        opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [hook],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }
            ]
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            base, _ = os.path.splitext(filename)
            return info, base + ".mp3"

    try:
        out_id = str(uuid.uuid4())[:8]
        outtmpl = f"downloads/{out_id}_%(title)s.%(ext)s"

        info, mp3file = await loop.run_in_executor(
            executor, lambda: do_download(entry["url"], outtmpl)
        )

    except Exception as e:
        USER_LOCKS.pop(user, None)
        return await progress_msg.edit_text(f"❌ Download failed: `{e}`")

    # -------------------------------------------------
    #            THUMB
    # -------------------------------------------------
    thumb = None
    if info.get("thumbnail"):
        try:
            r = requests.get(info["thumbnail"], timeout=10)
            if r.status_code == 200:
                thumb = mp3file.replace(".mp3", ".jpg")
                with open(thumb, "wb") as f:
                    f.write(r.content)
        except:
            thumb = None

    # -------------------------------------------------
    #              SEND AUDIO
    # -------------------------------------------------
    try:
        await progress_msg.edit_text("📤 Uploading…")

        artist = "💗...𓇢𓆸"
        caption = f">🎵 **{info.get('title')}**"

        # --- 1) Send to USER ---
        sent_message = await client.send_audio(
            chat_id=cq.message.chat.id,
            audio=mp3file,
            title=info.get("title"),
            performer=artist,
            thumb=thumb,
            caption=caption
        )

        # --- 2) Forward same file to CHANNEL (no need to re-upload) ---
        try:
            await sent_message.copy(
                chat_id=Config.MUSIC_CHANNEL
            )
        except Exception as err:
            print("Channel Upload Error:", err)

    except Exception as e:
        
        print("Upload Error:", e)

        await progress_msg.edit_text("✅ **Uploaded Successfully!**")

    except Exception as e:
        await progress_msg.edit_text(f"❌ Upload error: `{e}`")
        
        await status.delete()

    # Cleanup
    try:
        if os.path.exists(mp3file): os.remove(mp3file)
        if thumb and os.path.exists(thumb): os.remove(thumb)
    except:
        pass

    USER_LOCKS.pop(user, None)
    SEARCH_CACHE.pop(search_id, None)


