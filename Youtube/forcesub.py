import asyncio
from pyrogram import Client, enums
from Youtube.config import Config
from pyrogram.errors import FloodWait, UserNotParticipant
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton


########################🎊 Lisa | NT BOTS 🎊######################################################

async def handle_force_subscribe(bot, message):
    try:
        invite_link = await bot.create_chat_invite_link(int(Config.CHANNEL))
    except FloodWait as e:
        await asyncio.sleep(e.x)
        return 400
    try:
        user = await bot.get_chat_member(int(Config.CHANNEL), message.from_user.id)
        if user.status == "kicked":
            await bot.send_message(
                chat_id=message.from_user.id,
                text="Sorry, You are Banned. Contact Owner.",
                disable_web_page_preview=True,
            )
            return 400
    except UserNotParticipant:
        await bot.send_message(
            chat_id=message.from_user.id,
            text="Jᴏɪɴ Uᴘᴅᴀᴛᴇs Cʜᴀɴɴᴇʟ Tᴏ Usᴇ Mᴇ!\n\nDᴜᴇ ᴛᴏ Oᴠᴇʀʟᴏᴀᴅ, Oɴʟʏ Cʜᴀɴɴᴇʟ Sᴜʙsᴄʀɪʙᴇʀs Cᴀɴ Usᴇ Mᴇ!",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("🤖  Jᴏɪɴ Cʜᴀɴɴᴇʟ 🤖", url=invite_link.invite_link)
                    ],
                ]
            ),
            
        )
        return 400
    except Exception:
        await bot.send_message(
            chat_id=message.from_user.id,
            text="Something Went Wrong. Contact My Owner.",
            disable_web_page_preview=True,
        )
        return 400




def humanbytes(size):
    if not size:
        return "0 B"
    power = 2 ** 10
    n = 0
    Dic_powerN = {0: '', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {Dic_powerN[n]}B"





########################🎊 Lisa | NT BOTS 🎊######################################################
