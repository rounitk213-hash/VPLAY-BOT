import os
import asyncio
import uuid
import zipfile
import shutil
from datetime import datetime
import pytz

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import VideoQuality, AudioQuality

import motor.motor_asyncio
import certifi
import logging

# ================= CONFIG =================
BOT_TOKEN = "8750070865:AAE6GCrL9x9LDVmylCMQcClI_YPV1sTA8jE"
API_ID = 30191201
API_HASH = "5c87a8808e935cc3d97958d0bb24ff1f"
ASSISTANT_SESSION = "1BVtsOMUBu6rQhTgplBCsOAercwLtgCEO30snXlYnF8jSxnYbMQj2WBSbXHAtpJ1J_AAQ7rHXnPctvLORYrEpKyBo4rXEwoF2am8PogN7cddpdHcfwmj10kxnRZV4gDnehVIWA6P6yYh_5wGl01K8YUoEobNcH_5FJqG0jeZ_g5AhN0gT-JvQClPkRcFixnj8sAIHWwInc4cakHaBCB7VACMrZz0aSIwgH-7CAqHypYTo-p9EpczKkv5-kIWc2rPYApkzVzjH53sVxyM5o_1J8qn39zCWlcauzDMyaT6tIpJhTLNyiWA-EoJiMTljPMoESKKtbt8sF5OnXB4fd3U5J2hvb8vioAQ="

IST = pytz.timezone('Asia/Kolkata')
MONGO_URI = "mongodb+srv://bsdk:betichod@cluster0.fgj1r9z.mongodb.net/?retryWrites=true&w=majority"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= MONGODB =================
class DB:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
        self.db = self.client["video_bot_final"]
        self.batches = self.db.batches
        self.users = self.db.users
        self.temp_batch = self.db.temp_batch

db = DB()

# ================= GLOBALS =================
bot = None
assistant = None
call = None

# ================= UTILS =================
def format_size(size):
    if size < 1024*1024:
        return f"{size/1024:.1f}KB"
    elif size < 1024*1024*1024:
        return f"{size/(1024*1024):.1f}MB"
    else:
        return f"{size/(1024*1024*1024):.2f}GB"

def progress_bar(current, total, length=12):
    if total == 0:
        return "█░░░░░░░░░░░ 0%"
    percent = current / total
    filled = int(length * percent)
    bar = "█" * filled + "░" * (length - filled)
    return f"{bar} {int(percent * 100)}%"

def generate_id():
    return uuid.uuid4().hex[:5]

async def get_user_group(user_id):
    user = await db.users.find_one({"_id": user_id})
    if user:
        return user.get("group_id")
    return None

async def force_restart_voice(chat_id):
    try:
        await call.leave_call(chat_id)
        await asyncio.sleep(1)
    except:
        pass
    
    try:
        await call.join_call(chat_id)
        await asyncio.sleep(1)
        return True
    except Exception as e:
        logger.error(f"Join error: {e}")
        return False

async def play_video_high_quality(chat_id, file_path, title):
    try:
        await force_restart_voice(chat_id)
        
        media = MediaStream(
            file_path,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p
        )
        
        await call.play(chat_id, media)
        logger.info(f"✅ Playing: {title}")
        return True
        
    except Exception as e:
        logger.error(f"Play error: {e}")
        return False

async def play_batch(batch_id, user_id, status_msg):
    group_id = await get_user_group(user_id)
    if not group_id:
        await status_msg.edit("❌ Group not set! Use /setgroup -100xxxxx")
        return
    
    batch = await db.batches.find_one({"_id": batch_id, "user_id": user_id})
    if not batch:
        await status_msg.edit(f"❌ Collection `{batch_id}` not found!")
        return
    
    videos = batch.get('videos', [])
    total = len(videos)
    
    if total == 0:
        await status_msg.edit(f"❌ No videos found!")
        return
    
    await status_msg.edit(f"🎬 Playing {total} videos in HD...")
    
    for i, video in enumerate(videos, 1):
        if not os.path.exists(video['file_path']):
            await status_msg.edit(f"⚠️ Video {i} missing, skipping...")
            continue
        
        await status_msg.edit(f"🎬 [{i}/{total}] `{video['name'][:25]}`\n🎚️ HD 720p")
        
        success = await play_video_high_quality(group_id, video['file_path'], video['name'])
        
        if success:
            wait_time = max(12, int(video['file_size'] / (1024 * 1024)) * 1.2)
            
            for remaining in range(int(wait_time), 0, -5):
                await status_msg.edit(f"🎬 [{i}/{total}] `{video['name'][:25]}`\n⏱️ {remaining}s left")
                await asyncio.sleep(5)
        else:
            await status_msg.edit(f"❌ Failed: {video['name'][:20]}")
            await asyncio.sleep(2)
    
    await status_msg.edit(f"✅ Finished {total} videos!")
    await asyncio.sleep(2)
    await status_msg.delete()

# ================= COMMANDS =================
async def main():
    global bot, assistant, call
    
    logger.info("=" * 50)
    logger.info("Starting VIDEO BOT...")
    
    bot = TelegramClient('bot_session', API_ID, API_HASH)
    assistant = TelegramClient(StringSession(ASSISTANT_SESSION), API_ID, API_HASH)
    
    await bot.start(bot_token=BOT_TOKEN)
    logger.info(f"✅ Bot started")
    
    await assistant.start()
    logger.info("✅ Assistant started")
    
    call = PyTgCalls(assistant)
    await call.start()
    logger.info("✅ Voice client ready")
    
    @bot.on(events.NewMessage(pattern=r'^/start$'))
    async def start_cmd(event):
        if not event.is_private:
            return
        await event.reply("""
🎬 **VIDEO BOT**

**How to use:**
1. Send videos OR zip files
2. Type `/done` to save as collection
3. `/play <id>` plays all videos

**Commands:**
• `/setgroup -100xxxxx` - Set group
• `/done` - Save current videos
• `/play <id>` - Play collection
• `/collections` - List all
• `/delete <id>` - Delete
• `/clear` - Delete all
• `/cancel` - Cancel current

**Supports:** MP4, MKV, AVI, MOV + ZIP files
        """)
    
    @bot.on(events.NewMessage(pattern=r'^/setgroup(?: |$)(.*)'))
    async def setgroup_cmd(event):
        if not event.is_private:
            return
        args = event.pattern_match.group(1).strip()
        if not args:
            await event.reply("Usage: `/setgroup -100123456789`")
            return
        try:
            group_id = int(args)
            await db.users.update_one(
                {"_id": event.chat_id},
                {"$set": {"group_id": group_id}},
                upsert=True
            )
            await event.reply(f"✅ Group saved!")
        except:
            await event.reply("❌ Invalid group ID!")
    
    @bot.on(events.NewMessage(pattern=r'^/done$'))
    async def done_cmd(event):
        if not event.is_private:
            return
        
        user_id = event.chat_id
        temp = await db.temp_batch.find_one({"user_id": user_id})
        
        if not temp:
            await event.reply("📭 No videos found! Send videos or zip files first.")
            return
        
        videos = temp.get('videos', [])
        
        if not videos:
            await event.reply("📭 No videos in batch!")
            return
        
        batch_id = generate_id()
        batch_name = f"Collection_{batch_id}"
        
        batch_folder = os.path.join(DOWNLOAD_DIR, f"batch_{batch_id}")
        os.makedirs(batch_folder, exist_ok=True)
        
        final_videos = []
        for v in videos:
            old_path = v['file_path']
            new_name = f"{uuid.uuid4().hex}.mp4"
            new_path = os.path.join(batch_folder, new_name)
            
            if os.path.exists(old_path):
                shutil.move(old_path, new_path)
                final_videos.append({
                    "file_path": new_path,
                    "name": v.get('name', f"Video_{uuid.uuid4().hex[:4]}"),
                    "original_name": v.get('original_name', 'Unknown'),
                    "file_size": v.get('file_size', 0)
                })
        
        total_size = sum(v['file_size'] for v in final_videos)
        
        await db.batches.insert_one({
            "_id": batch_id,
            "user_id": user_id,
            "name": batch_name,
            "videos": final_videos,
            "video_count": len(final_videos),
            "total_size": total_size,
            "created_at": datetime.now(IST)
        })
        
        await db.temp_batch.delete_one({"user_id": user_id})
        
        await event.reply(f"""
✅ **Collection Saved!**

🗜️ **ID:** `{batch_id}`
📹 **Videos:** `{len(final_videos)}`
💾 **Size:** `{format_size(total_size)}`

**Play all:** `/play {batch_id}`
        """)
    
    @bot.on(events.NewMessage(pattern=r'^/cancel$'))
    async def cancel_cmd(event):
        if not event.is_private:
            return
        
        user_id = event.chat_id
        temp = await db.temp_batch.find_one({"user_id": user_id})
        
        if temp:
            for v in temp.get('videos', []):
                try:
                    if os.path.exists(v['file_path']):
                        os.remove(v['file_path'])
                except:
                    pass
            await db.temp_batch.delete_one({"user_id": user_id})
            await event.reply("🗑️ Current batch cancelled!")
        else:
            await event.reply("📭 No active batch.")
    
    @bot.on(events.NewMessage(pattern=r'^/play(?: |$)(.*)'))
    async def play_cmd(event):
        if not event.is_private:
            return
        
        args = event.pattern_match.group(1).strip()
        if not args:
            await event.reply("Usage: `/play <collection_id>`")
            return
        
        status_msg = await event.reply(f"🎬 Loading...")
        
        batch = await db.batches.find_one({"_id": args, "user_id": event.chat_id})
        if batch:
            await play_batch(args, event.chat_id, status_msg)
            return
        
        await status_msg.edit(f"❌ `{args}` not found!")
    
    @bot.on(events.NewMessage(pattern=r'^/collections$'))
    async def collections_cmd(event):
        if not event.is_private:
            return
        
        batches = await db.batches.find({"user_id": event.chat_id}).to_list(100)
        
        if not batches:
            await event.reply("📭 No collections!")
            return
        
        msg = f"**📦 COLLECTIONS** ({len(batches)})\n\n"
        for b in batches[:20]:
            vcount = b.get('video_count', 0)
            total_size = format_size(b.get('total_size', 0))
            msg += f"🗜️ `{b['_id']}` - {vcount} videos | {total_size}\n"
        
        await event.reply(msg)
    
    @bot.on(events.NewMessage(pattern=r'^/delete(?: |$)(.*)'))
    async def delete_cmd(event):
        if not event.is_private:
            return
        
        args = event.pattern_match.group(1).strip()
        if not args:
            await event.reply("Usage: `/delete <collection_id>`")
            return
        
        batch = await db.batches.find_one({"_id": args, "user_id": event.chat_id})
        if batch:
            for video in batch.get('videos', []):
                try:
                    if os.path.exists(video['file_path']):
                        os.remove(video['file_path'])
                except:
                    pass
            
            folder = os.path.join(DOWNLOAD_DIR, f"batch_{args}")
            try:
                shutil.rmtree(folder)
            except:
                pass
            
            await db.batches.delete_one({"_id": args})
            await event.reply(f"✅ Deleted!")
            return
        
        await event.reply(f"❌ Not found!")
    
    @bot.on(events.NewMessage(pattern=r'^/clear$'))
    async def clear_cmd(event):
        if not event.is_private:
            return
        
        user_id = event.chat_id
        
        batches = await db.batches.find({"user_id": user_id}).to_list(200)
        for b in batches:
            folder = os.path.join(DOWNLOAD_DIR, f"batch_{b['_id']}")
            try:
                shutil.rmtree(folder)
            except:
                pass
        
        temp = await db.temp_batch.find_one({"user_id": user_id})
        if temp:
            for v in temp.get('videos', []):
                try:
                    if os.path.exists(v['file_path']):
                        os.remove(v['file_path'])
                except:
                    pass
            await db.temp_batch.delete_one({"user_id": user_id})
        
        result = await db.batches.delete_many({"user_id": user_id})
        await event.reply(f"🗑️ Deleted {result.deleted_count} collections!")
    
    # ================ VIDEO HANDLER ================
    
    @bot.on(events.NewMessage)
    async def file_handler(event):
        if not event.is_private:
            return
        
        user_id = event.chat_id
        
        # ========== ZIP FILE HANDLER ==========
        if event.message.document and event.message.document.mime_type == 'application/zip':
            file_size = event.message.document.size
            original_name = event.message.file.name or f"zip_{uuid.uuid4().hex[:6]}.zip"
            
            status_msg = await event.reply(f"""
📦 **Processing Zip...** | `{original_name[:20]}`

`█░░░░░░░░░░░ 0%`

⬇️ Downloading...
            """)
            
            zip_path = os.path.join(DOWNLOAD_DIR, f"zip_{user_id}_{uuid.uuid4().hex}.zip")
            
            # Download with progress
            last_pct = 0
            async def progress_cb(current, total):
                nonlocal last_pct
                if total > 0:
                    pct = int((current / total) * 100)
                    if pct - last_pct >= 10:
                        last_pct = pct
                        bar = progress_bar(current, total)
                        try:
                            asyncio.create_task(status_msg.edit(f"""
📦 **Processing Zip...** | `{original_name[:20]}` | {format_size(total)}

`{bar}`

⬇️ {format_size(current)} / {format_size(total)}
                            """))
                        except:
                            pass
            
            await event.message.download_media(file=zip_path, progress_callback=progress_cb)
            
            if not os.path.exists(zip_path):
                await status_msg.edit("❌ Download failed!")
                return
            
            await status_msg.edit(f"📦 Extracting zip file...")
            
            # Extract zip
            extract_folder = os.path.join(DOWNLOAD_DIR, f"extract_{user_id}_{uuid.uuid4().hex}")
            os.makedirs(extract_folder, exist_ok=True)
            
            extracted_videos = []
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    video_files = [f for f in zf.namelist() if f.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm'))]
                    total = len(video_files)
                    
                    for i, file_info in enumerate(video_files, 1):
                        bar = progress_bar(i, total)
                        await status_msg.edit(f"""
📦 **Extracting Zip...** | `{original_name[:20]}`

`{bar}`

📹 Found: {i}/{total} videos
                        """)
                        
                        extracted_path = zf.extract(file_info, extract_folder)
                        extracted_videos.append(extracted_path)
                        await asyncio.sleep(0.05)
                
                os.remove(zip_path)
                
            except Exception as e:
                await status_msg.edit(f"❌ Extract failed: {str(e)[:50]}")
                return
            
            if not extracted_videos:
                await status_msg.edit("❌ No video files found in zip!")
                shutil.rmtree(extract_folder)
                return
            
            # Add each extracted video to temp batch
            temp = await db.temp_batch.find_one({"user_id": user_id})
            added_count = 0
            
            for v_path in extracted_videos:
                video_name = f"ZipVideo_{uuid.uuid4().hex[:4]}"
                file_size = os.path.getsize(v_path)
                
                if not temp:
                    await db.temp_batch.insert_one({
                        "user_id": user_id,
                        "videos": [{
                            "file_path": v_path,
                            "name": video_name,
                            "original_name": os.path.basename(v_path),
                            "file_size": file_size
                        }],
                        "created_at": datetime.now(IST)
                    })
                    temp = await db.temp_batch.find_one({"user_id": user_id})
                else:
                    await db.temp_batch.update_one(
                        {"user_id": user_id},
                        {"$push": {"videos": {
                            "file_path": v_path,
                            "name": video_name,
                            "original_name": os.path.basename(v_path),
                            "file_size": file_size
                        }}}
                    )
                added_count += 1
            
            # Get total count
            final_temp = await db.temp_batch.find_one({"user_id": user_id})
            total_videos = len(final_temp.get('videos', [])) if final_temp else 0
            total_size = sum(v['file_size'] for v in final_temp.get('videos', [])) if final_temp else 0
            
            await status_msg.edit(f"""
✅ **Zip Extracted!** | {added_count} videos added

📹 **From zip:** `{original_name[:25]}`
➕ **Added:** `{added_count}` videos

📊 **Current batch:** `{total_videos}` videos | `{format_size(total_size)}`

Type `/done` to save this collection!
            """)
            
            await asyncio.sleep(5)
            await status_msg.delete()
            return
        
        # ========== SINGLE VIDEO HANDLER ==========
        if event.message.video:
            video = event.message.video
            original_name = event.message.file.name if event.message.file else f"video_{uuid.uuid4().hex[:6]}.mp4"
            file_size = video.size
            
            status_msg = await event.reply(f"""
📥 **Downloading...** | `{original_name[:20]}`

`█░░░░░░░░░░░ 0%`
            """)
            
            filepath = os.path.join(DOWNLOAD_DIR, f"temp_{user_id}_{uuid.uuid4().hex}.mp4")
            
            last_pct = 0
            async def progress_cb(current, total):
                nonlocal last_pct
                if total > 0:
                    pct = int((current / total) * 100)
                    if pct - last_pct >= 10:
                        last_pct = pct
                        bar = progress_bar(current, total)
                        try:
                            asyncio.create_task(status_msg.edit(f"""
📥 **Downloading...** | `{original_name[:20]}`

`{bar}`

⬇️ {format_size(current)} / {format_size(total)}
                            """))
                        except:
                            pass
            
            await event.message.download_media(file=filepath, progress_callback=progress_cb)
            
            if not os.path.exists(filepath):
                await status_msg.edit("❌ Download failed!")
                return
            
            video_name = f"Vid_{uuid.uuid4().hex[:4]}"
            temp = await db.temp_batch.find_one({"user_id": user_id})
            
            if not temp:
                await db.temp_batch.insert_one({
                    "user_id": user_id,
                    "videos": [{
                        "file_path": filepath,
                        "name": video_name,
                        "original_name": original_name,
                        "file_size": file_size
                    }],
                    "created_at": datetime.now(IST)
                })
                count = 1
            else:
                await db.temp_batch.update_one(
                    {"user_id": user_id},
                    {"$push": {"videos": {
                        "file_path": filepath,
                        "name": video_name,
                        "original_name": original_name,
                        "file_size": file_size
                    }}}
                )
                count = len(temp.get('videos', [])) + 1
            
            updated_temp = await db.temp_batch.find_one({"user_id": user_id})
            total_size = sum(v['file_size'] for v in updated_temp.get('videos', []))
            
            await status_msg.edit(f"""
✅ **Video Added!** (#{count})

📹 `{original_name[:30]}`
📦 Size: `{format_size(file_size)}`

📊 **Batch:** `{count}` videos | `{format_size(total_size)}` total

Type `/done` to save this collection!
            """)
            
            await asyncio.sleep(4)
            try:
                await status_msg.delete()
            except:
                pass
            return
    
    logger.info("=" * 50)
    logger.info("🎬 VIDEO BOT READY!")
    logger.info("✅ Single videos work")
    logger.info("✅ ZIP files work (extracts all videos)")
    logger.info("✅ /done creates collection")
    logger.info("✅ /play <id> plays all")
    logger.info("=" * 50)
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except Exception as e:
        logger.error(f"Error: {e}")
