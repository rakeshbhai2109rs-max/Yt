# ==========================================================
#  ©️ LISA-KOREA | Playlist Downloader Module
#  Compatible with YouTube-Video-Download-Bot
# ==========================================================

import os
import aiofiles
import aiohttp
import asyncio
import logging
import uuid
from pyrogram import Client, filters
import yt_dlp
from Youtube.config import Config
from Youtube.forcesub import handle_force_subscribe
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
import pyrogram




playlist_cache = {}  # Add this at the top of the file


# ========== Helper ==========
def humanbytes(size):
    if not size:
        return "0 B"
    power = 1000
    n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    while size >= power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {units[n]}"


playlist_id = str(uuid.uuid4())[:8]  # Generate a unique ID for this playlist

# Then create buttons
kb = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🎵 Audio MP3 128kbps", callback_data=f"pl_dl_audio_128_{playlist_id}"),
        InlineKeyboardButton("🎵 Audio MP3 320kbps", callback_data=f"pl_dl_audio_320_{playlist_id}")
    ],
    [
        InlineKeyboardButton("🎬 Video 720p MP4", callback_data=f"pl_dl_video_720_{playlist_id}"),
        InlineKeyboardButton("🎬 Video 1080p MP4", callback_data=f"pl_dl_video_1080_{playlist_id}")
    ]
])

# ========== Main Handler ==========
@Client.on_message(filters.command(["playlist", "pl"]))
async def playlist_downloader(client, message):
    # If you still want to enforce force-subscribe for private chats
    if Config.CHANNEL and message.chat.type == "private":
        fsub = await handle_force_subscribe(client, message)
        if fsub == 400:
            return

    # Validate command
    if len(message.command) < 2:
        await message.reply_text(
            "🎵 *Usage:*\n`/playlist <YouTube Playlist URL>`",
            disable_web_page_preview=True,
        )
        return

    playlist_url = message.text.split(maxsplit=1)[1].strip()
    processing_msg = await message.reply_text("🔍 **Fetching playlist details...**")

    try:
        os.makedirs("downloads/playlists", exist_ok=True)
        playlist_id = str(uuid.uuid4())[:8]
        playlist_folder = os.path.join("downloads", "playlists", playlist_id)

        ydl_opts = {
            "quiet": True,
            "extract_flat": False,
            "cookiefile": "cookies.txt",
            "ignoreerrors": True,
            "outtmpl": os.path.join(playlist_folder, "%(playlist_index)s - %(title)s.%(ext)s"),
            "retries": 5,
            "socket_timeout": 90,
        }

        # Fetch playlist info (no download yet)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries", [])
            title = f"⚝ {info.get('title', 'YouTube Video')}"
            total_videos = len(entries)

        new_text = f"🎶 Playlist: {title}\n📦 Link Found: {total_videos}"

        # Only edit if text actually changed
        if processing_msg.text != new_text:
            try:
                await processing_msg.edit_text(
                    new_text,
                   
                )
            except pyrogram.errors.MessageNotModified:
                pass  # silently ignore if nothing changed

                    
                

        # Save the URL to cache to keep callback short
        playlist_cache[playlist_id] = playlist_url

        # Inline buttons with short callback
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎵 Audio MP3 128kbps", callback_data=f"pl_dl_audio_128_{playlist_id}"),
                InlineKeyboardButton("🎵 Audio MP3 320kbps", callback_data=f"pl_dl_audio_320_{playlist_id}")
            ],
            [
                InlineKeyboardButton("🎬 Video 720p MP4", callback_data=f"pl_dl_video_720_{playlist_id}"),
                InlineKeyboardButton("🎬 Video 1080p MP4", callback_data=f"pl_dl_video_1080_{playlist_id}")
            ]
        ])

        await message.reply_text("⬇️ Select format to download:", reply_markup=kb)
        await processing_msg.delete()

    except Exception as e:
        logging.exception("Error fetching playlist:")
        await processing_msg.edit_text(f"❌ Error: `{e}`")


# ========== Playlist Download Handler ==========
@Client.on_callback_query(filters.regex(r"^pl_dl_"))
async def handle_playlist_download(client, cq):
    try:
        parts = cq.data.split("_")
        if len(parts) < 4:
            await cq.message.edit_text("❌ Invalid callback data.")
            return

        media_type = parts[2]

        # Determine quality/resolution
        if len(parts) == 5:
            quality = parts[3]
            pl_id = parts[4]
        else:  # len(parts) == 4
            quality = None
            pl_id = parts[3]

        playlist_url = playlist_cache.get(pl_id)
        if not playlist_url:
            await cq.message.edit_text("❌ Playlist expired or invalid.")
            return

        await cq.message.edit_text(f"⬇️ Downloading playlist in {media_type.upper()} {quality or ''}...")

        # Create folder for playlist
        folder_path = os.path.join("downloads/playlists", str(uuid.uuid4())[:8])
        os.makedirs(folder_path, exist_ok=True)
        output = os.path.join(folder_path, "%(title)s.%(ext)s")

        # yt-dlp options
        if media_type == "audio":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output,
                "quiet": True,
                "cookiefile": "cookies.txt",
                "ignoreerrors": True,
                "retries": 5,
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": quality},
                    {"key": "FFmpegMetadata"}
                ],
            }
        else:
            if quality == "720":
                fmt = "bestvideo[height<=720]+bestaudio/best"
            elif quality == "1080":
                fmt = "bestvideo[height<=1080]+bestaudio/best"
            else:
                fmt = "bestvideo+bestaudio/best"

            ydl_opts = {
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": output,
                "quiet": True,
                "cookiefile": "cookies.txt",
                "ignoreerrors": True,
                "retries": 5,
                "postprocessors": [{"key": "FFmpegMetadata"}],
            }

        # Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=True)
            entries = info.get("entries", [])

            for idx, entry in enumerate(entries, start=1):
                # Get correct file path after postprocessing
                file_path = ydl.prepare_filename(entry)
                if media_type == "audio":
                    base, _ = os.path.splitext(file_path)
                    file_path = base + ".mp3"  # ensure Telegram playable audio

                if os.path.exists(file_path):
                    size_text = humanbytes(os.path.getsize(file_path))
                    caption = f"<b>{entry.get('title', 'Audio/Video')}</b>\n>📥 Size: {size_text}"

                    if media_type == "audio":
                        # Send to user
                       # First send to user
                        await client.send_audio(
                            chat_id=cq.message.chat.id,
                            audio=mp3file,
                            title=info.get("title"),
                            performer=artist,
                            thumb=thumb,
                            caption=f"🎵 **{info.get('title')}**"
                        )

                        # Now check channel before sending
                        title = info.get("title")

                        if not await already_uploaded(client, Config.MUSIC_CHANNEL, title):
                            try:
                                await client.send_audio(
                                    chat_id=Config.MUSIC_CHANNEL,
                                    audio=mp3file,
                                    title=title,
                                    performer=artist,
                                    thumb=thumb,
                                    caption=f"🎵 **{title}**"
                                )
                            except Exception as e:
                                print("Channel Upload Error:", e)
                        else:
                            print("Skipped: Already exists in channel")

                        
                    else:
                        await client.send_video(
                            chat_id=cq.message.chat.id,
                            video=file_path,
                            caption=caption
                        )

                    os.remove(file_path)  # cleanup after sending

        playlist_cache.pop(pl_id, None)
        await cq.message.edit_text("✅ Playlist download complete!")

    except Exception as e:
        logging.exception("Playlist error:")
        await cq.message.edit_text(f"❌ Error: {e}")
