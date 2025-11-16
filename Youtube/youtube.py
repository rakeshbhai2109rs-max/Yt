# ©️ LISA-KOREA | @LISA_FAN_LK | NT_BOT_CHANNEL | LISA-KOREA/YouTube-Video-Download-Bot
# [⚠️ Do not change this repo link ⚠️] :- https://github.com/LISA-KOREA/YouTube-Video-Download-Bot

import os
import yt_dlp
import logging
import uuid
import aiohttp
import aiofiles
import time
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from Youtube.config import Config
from Youtube.fix_thumb import fix_thumb
from Youtube.forcesub import handle_force_subscribe, humanbytes
import subprocess
import math


YT_CACHE = {}

# ══════════════════════════════════════════════════════════════
# 🔹 MESSAGE HANDLER — Fetch available formats
# ══════════════════════════════════════════════════════════════
@Client.on_message(filters.regex(r'^(http(s)?://)?(www\.)?(youtube\.com|youtu\.be)/.+'))
async def youtube_downloader(client, message):
    if Config.CHANNEL:
        fsub = await handle_force_subscribe(client, message)
        if fsub == 400:
            return

    url = message.text.strip()
    processing_msg = await message.reply_text("🔍 **Fetching available formats...**")

    ydl_opts = {"quiet": True, "no_warnings": True, "cookiefile": "cookies.txt", "nocheckcertificate": True}
    buttons = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            duration = info.get("duration") or 0
            title = info.get("title", "YouTube Video")

            vid_key = str(uuid.uuid4())[:8]
            YT_CACHE[vid_key] = url

            for f in formats:
                fmt_id = f.get("format_id")
                ext = f.get("ext")
                note = f.get("format_note") or ""
                height = f.get("height")
                fps = f.get("fps")
                vbr = f.get("tbr") or f.get("vbr") or 0
                size = f.get("filesize") or f.get("filesize_approx")

                if not fmt_id or "storyboard" in str(note).lower():
                    continue

                res = f"{height}p" if height else "Unknown"

                if not size and duration and vbr:
                    size = (vbr * 1000 / 8) * duration

                size_text = humanbytes(size) if size else "Unknown"
                fps_text = f"{fps}fps" if fps else ""
                text = f"{res} {fps_text} • {size_text}".strip()

                cb = f"ytdl|{vid_key}|{fmt_id}|{ext}|video"
                if len(cb.encode()) <= 64:
                    buttons.append([InlineKeyboardButton(text, callback_data=cb)])

            buttons.append([
                InlineKeyboardButton("🎵 Audio MP3", callback_data=f"ytdl|{vid_key}|bestaudio|mp3|audio")
            ])

            await message.reply_text(
                f"**✅ Available formats for:**\n`{title}`",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

            await processing_msg.delete()

    except Exception as e:
        logging.exception("Error fetching formats:")
        await processing_msg.edit_text(f"❌ Error: `{e}`")


MAX_SIZE = 2_147_483_648  # 2GB


def split_video(file_path):
    filesize = os.path.getsize(file_path)
    if filesize <= MAX_SIZE:
        return [file_path]

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    total_duration = float(result.stdout)
    num_chunks = math.ceil(filesize / MAX_SIZE)
    chunk_duration = total_duration / num_chunks

    base_name, ext = os.path.splitext(file_path)
    chunk_files = []

    for i in range(num_chunks):
        output_file = f"{base_name}_part{i+1}{ext}"
        cmd = [
            "ffmpeg", "-i", file_path,
            "-ss", str(i * chunk_duration),
            "-t", str(chunk_duration),
            "-c", "copy", "-y",
            output_file
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(output_file):
            chunk_files.append(output_file)

    return chunk_files


# ══════════════════════════════════════════════════════════════
# 🔹 DOWNLOAD + UPLOAD HANDLER
# ══════════════════════════════════════════════════════════════
@Client.on_callback_query(filters.regex(r"^ytdl\|"))
async def handle_download(client, cq):

    try:
        _, vid_key, fmt_id, ext, mode = cq.data.split("|")
        url = YT_CACHE.get(vid_key)

        if not url:
            await cq.message.edit_text("⚠️ Session expired. Please resend link.")
            return

        await cq.message.edit_text("⬇️ **Downloading...**")

        os.makedirs("downloads", exist_ok=True)
        output = os.path.join("downloads", "%(title)s.%(ext)s")

        common_opts = {
            "outtmpl": output,
            "quiet": True,
            "cookiefile": "cookies.txt",
            "nocheckcertificate": True,
            "retries": 5,
            "socket_timeout": 30,
            "noprogress": True,
            "concurrent_fragment_downloads": 3,
        }

        if mode == "audio":
            ydl_opts = {
                **common_opts,
                "format": "bestaudio/best",
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                    {"key": "FFmpegMetadata"}
                ],
            }
        else:
            ydl_opts = {
                **common_opts,
                "format": fmt_id,
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata"}],
            }

        # DOWNLOAD
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "YouTube Video")
            duration = info.get("duration", 0)
            width = info.get("width")
            height = info.get("height")
            thumb_url = info.get("thumbnail")
            file_path = ydl.prepare_filename(info)

            if not os.path.exists(file_path):
                base, _ = os.path.splitext(file_path)
                for ext_check in (".mp3", ".m4a", ".mp4", ".webm"):
                    if os.path.exists(base + ext_check):
                        file_path = base + ext_check
                        break

        # DOWNLOAD THUMB
        thumb_path = None
        if thumb_url:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(thumb_url, timeout=15) as r:
                        if r.status == 200:
                            thumb_path = f"{vid_key}.jpg"
                            async with aiofiles.open(thumb_path, "wb") as f:
                                await f.write(await r.read())
            except Exception:
                pass

        width, height, thumb_path = await fix_thumb(thumb_path)

        await cq.message.edit_text("📤 **Uploading...**")

        safe_path = os.path.normpath(file_path)

        # ════════════════
        # AUDIO UPLOAD
        # ════════════════
        if mode == "audio":
            artist = "⚝...𓇢𓆸"
            caption = f"🎵 **{title}**"

            sent = await client.send_audio(
                chat_id=cq.message.chat.id,
                audio=safe_path,
                caption=caption,
                performer=artist,
                title=title,
                duration=duration,
                thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
            )

            # Forward same file to channel (no re-upload)
            try:
                await sent.copy(chat_id=Config.MUSIC_CHANNEL)
            except Exception as err:
                print("Channel Upload Error:", err)

        else:
            # ════════════════
            # VIDEO UPLOAD
            # ════════════════
            chunk_files = split_video(safe_path)

            for idx, chunk in enumerate(chunk_files, start=1):

                if len(chunk_files) > 1:
                    caption = f"🎬 **{title}** (Part {idx}/{len(chunk_files)})"
                else:
                    caption = f"🎬 **{title}**"

                await client.send_video(
                    chat_id=cq.message.chat.id,
                    video=chunk,
                    caption=caption,
                    width=width or 1280,
                    height=height or 720,
                    duration=duration,
                    thumb=thumb_path if thumb_path and os.path.exists(thumb_path) else None,
                    supports_streaming=True,
                    has_spoiler=True,
                )

                os.remove(chunk)

        await cq.message.edit_text("✅ **Upload complete!**")

        # CLEANUP
        try:
            if os.path.exists(safe_path):
                os.remove(safe_path)
            if thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

    except Exception as e:
        logging.exception("Download error:")
        await cq.message.edit_text(f"❌ **Error:** `{e}`")
