import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from pytubefix import YouTube
import re
import os
import time
import requests

# ==================== ТОКЕНЫ ====================
GROUP_TOKEN = "vk1.a.Nk3OlAhTVgwIx3iycM9PNQ3dQBBgV260ji92f_4xQZfLCzluqt1-qL8yfousfJwzrosaA4R59Pjos6XxrsKXjsQ2d9Q379cdZ-gq6Uz65MrU2VMwxenIvdvSJnro4i0Y5cGFcDN87QdlZU1uwuRwIXG0xJHV0HdeiXKOouNsTDFw5RVzGmHRda3tGlLp3Zf7nR0tfXkG0XBMQqZvowdq8Q"
USER_TOKEN = "vk1.a.SPQ28VHw3XbhTDYgCo099SoTllyNg4lbWwumJSCrY6Sh3gM4pZgk2tdl3KhmtdIgZA-RjIPr5yJeh4jBNaD4jSJKWKMNM6H7jnwknWA5BjXPHjfou3mrTdj3C7e08B4HwQfzRMseL33Y503D2Qb6HypWw8P4GGXqouefDxY3oHvGiHWaDVi_-tz4042s7FtRQd3xfkecoD_DYDRoY-Je8g"
GROUP_ID = 237434364

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Инициализация API
vk_group_session = vk_api.VkApi(token=GROUP_TOKEN)
vk_group = vk_group_session.get_api()
vk_user_session = vk_api.VkApi(token=USER_TOKEN)
vk_user = vk_user_session.get_api()
longpoll = VkLongPoll(vk_group_session)

# ==================== ФУНКЦИИ ====================
def extract_youtube_url(text):
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"
    return None

def download_video_720p(url):
    """Принудительно скачивает в 720p (лучшее качество с аудио)"""
    try:
        yt = YouTube(url)
        print(f"Скачивание: {yt.title}")
        
        # Пробуем 720p с аудио
        stream = yt.streams.filter(progressive=True, file_extension='mp4', res="720p").first()
        
        # Если 720p нет, берём лучшее доступное
        if not stream:
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        # Если вообще нет progressive, берём любой mp4
        if not stream:
            stream = yt.streams.filter(file_extension='mp4').first()
        
        if not stream:
            return None, None, None
        
        resolution = stream.resolution if stream.resolution else "Unknown"
        print(f"Качество: {resolution}")
        
        safe_title = re.sub(r'[\\/*?:"<>|]', "", yt.title)
        filename = os.path.join(DOWNLOAD_FOLDER, f"{safe_title}.mp4")
        
        stream.download(output_path=DOWNLOAD_FOLDER, filename=f"{safe_title}.mp4")
        
        return filename, yt.title, resolution
        
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return None, None, None

def upload_video_to_vk(video_file, title):
    try:
        save_data = vk_user.video.save(
            name=title[:100],
            description=f"Скачано с YouTube",
            group_id=GROUP_ID,
            is_private=0
        )
        
        with open(video_file, 'rb') as f:
            files = {'video_file': f}
            response = requests.post(save_data['upload_url'], files=files).json()
        
        attachment = f"video-{GROUP_ID}_{response['video_id']}"
        return attachment
    except Exception as e:
        print(f"Ошибка загрузки в ВК: {e}")
        return None

def send_message(vk, user_id, message, attachment=None):
    try:
        params = {
            "user_id": user_id,
            "message": message,
            "random_id": 0
        }
        if attachment:
            params["attachment"] = attachment
        vk.messages.send(**params)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ==================== ЗАПУСК ====================
print("=" * 60)
print("🎬 YouTube бот (720p) запущен!")
print("📁 Папка загрузок: downloads")
print("👀 Ожидание сообщений...")
print("=" * 60)

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text.strip()
        
        print(f"\n📨 Сообщение от {user_id}: {text[:50]}")
        
        video_url = extract_youtube_url(text)
        
        if not video_url:
            send_message(vk_group, user_id, "❌ Отправьте YouTube ссылку")
            continue
        
        send_message(vk_group, user_id, "📥 Скачиваю видео в 720p...")
        
        file_path, title, quality = download_video_720p(video_url)
        
        if not file_path or not os.path.exists(file_path):
            send_message(vk_group, user_id, "❌ Ошибка скачивания видео")
            continue
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        print(f"Размер видео: {file_size:.2f} MB | Качество: {quality}")
        
        if file_size > 1900:
            send_message(vk_group, user_id, f"⚠️ Видео слишком большое ({file_size:.0f}MB)\nВК не принимает файлы больше 2GB")
            os.remove(file_path)
            continue
        
        send_message(vk_group, user_id, f"📤 Загружаю {file_size:.1f}MB в ВК...")
        
        attachment = upload_video_to_vk(file_path, title)
        
        if attachment:
            send_message(vk_group, user_id, f"✅ Видео ({quality}) готово!", attachment)
        else:
            send_message(vk_group, user_id, "❌ Ошибка загрузки в ВК")
        
        time.sleep(3)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Удалён: {file_path}")