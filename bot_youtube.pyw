import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import yt_dlp
import re
import os
import time
import requests
import json
import sqlite3
import random
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ==================== ТОКЕНЫ И КЛЮЧИ ====================
GROUP_TOKEN = "vk1.a.Nk3OlAhTVgwIx3iycM9PNQ3dQBBgV260ji92f_4xQZfLCzluqt1-qL8yfousfJwzrosaA4R59Pjos6XxrsKXjsQ2d9Q379cdZ-gq6Uz65MrU2VMwxenIvdvSJnro4i0Y5cGFcDN87QdlZU1uwuRwIXG0xJHV0HdeiXKOouNsTDFw5RVzGmHRda3tGlLp3Zf7nR0tfXkG0XBMQqZvowdq8Q"
USER_TOKEN = "vk1.a.SPQ28VHw3XbhTDYgCo099SoTllyNg4lbWwumJSCrY6Sh3gM4pZgk2tdl3KhmtdIgZA-RjIPr5yJeh4jBNaD4jSJKWKMNM6H7jnwknWA5BjXPHjfou3mrTdj3C7e08B4HwQfzRMseL33Y503D2Qb6HypWw8P4GGXqouefDxY3oHvGiHWaDVi_-tz4042s7FtRQd3xfkecoD_DYDRoY-Je8g"
YOUTUBE_API_KEY = "AIzaSyC_mqbv3JEFrDx2PK8rO1Cu55KZ9uXFBeA"
GROUP_ID = 237434364

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ==================== БАЗА ДАННЫХ ====================
def init_database():
    """Инициализация базы данных просмотренных Shorts"""
    conn = sqlite3.connect('shorts_history.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS viewed_shorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            title TEXT,
            channel TEXT,
            viewed_at TIMESTAMP,
            viewed_by INTEGER,
            search_query TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shorts_stats (
            video_id TEXT PRIMARY KEY,
            views_count INTEGER DEFAULT 0,
            last_viewed TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def is_video_viewed(video_id):
    """Проверяет, смотрел ли кто-то это видео раньше"""
    conn = sqlite3.connect('shorts_history.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM viewed_shorts WHERE video_id = ?', (video_id,))
    count = cursor.fetchone()[0]
    
    conn.close()
    return count > 0

def add_viewed_video(video_id, title, channel, user_id, search_query=""):
    """Добавляет видео в историю просмотров"""
    conn = sqlite3.connect('shorts_history.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO viewed_shorts (video_id, title, channel, viewed_at, viewed_by, search_query)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (video_id, title, channel, datetime.now(), user_id, search_query))
        
        cursor.execute('''
            INSERT INTO shorts_stats (video_id, views_count, last_viewed)
            VALUES (?, 1, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                views_count = views_count + 1,
                last_viewed = ?
        ''', (video_id, datetime.now(), datetime.now()))
        
        conn.commit()
    except Exception as e:
        print(f"Ошибка БД: {e}")
    finally:
        conn.close()

def get_shorts_stats():
    """Получает статистику по просмотрам Shorts"""
    conn = sqlite3.connect('shorts_history.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT video_id), SUM(views_count) 
        FROM shorts_stats
    ''')
    unique_videos, total_views = cursor.fetchone()
    
    conn.close()
    return unique_videos or 0, total_views or 0

# Инициализация БД
init_database()

# Хранилище сессий пользователей
user_sessions = {}

# Русские ключевые слова для поиска Shorts
RUSSIAN_KEYWORDS = [
    "приколы", "смешное видео", "юмор", "мемы", "лайфхаки", "рецепты",
    "путешествия", "спорт", "музыка", "танцы", "животные", "котики",
    "собаки", "новости", "факты", "истории", "интервью", "блогеры",
    "тикток", "тренды", "челленджи", "вайны", "обзоры", "распаковка",
    "покупки", "макияж", "рецепты еды", "фитнес", "йога", "психология",
    "отношения", "дети", "игры", "технологии", "гаджеты", "авто",
    "ремонт", "стройка", "дача", "огород", "рукоделие", "рисование"
]

# ==================== ИНИЦИАЛИЗАЦИЯ VK И YOUTUBE ====================
vk_group_session = vk_api.VkApi(token=GROUP_TOKEN)
vk_group = vk_group_session.get_api()
vk_user_session = vk_api.VkApi(token=USER_TOKEN)
vk_user = vk_user_session.get_api()
longpoll = VkLongPoll(vk_group_session)

# Инициализация YouTube API
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("🔍 Поиск YouTube", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📱 FreeShorts", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("❓ Помощь", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("ℹ️ О боте", color=VkKeyboardColor.SECONDARY)
    return keyboard

def get_search_type_keyboard():
    """Клавиатура выбора типа поиска"""
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button("🎬 Видео", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("📺 Каналы", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    return keyboard

def get_channel_videos_keyboard(channel_id, page=0):
    """Клавиатура для навигации по видео канала"""
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("⬇️ Следующие видео", color=VkKeyboardColor.PRIMARY)
    if page > 0:
        keyboard.add_button("⬆️ Предыдущие видео", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("🔍 Новый поиск", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    return keyboard

def get_navigation_keyboard(current_start, total_items=100):
    keyboard = VkKeyboard(one_time=False)
    
    if current_start > 0:
        keyboard.add_button("⬆️ Вверх", color=VkKeyboardColor.SECONDARY)
    if current_start + 10 < total_items:
        keyboard.add_button("⬇️ Вниз", color=VkKeyboardColor.SECONDARY)
    
    keyboard.add_line()
    keyboard.add_button("🔍 Новый поиск", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard

def get_video_control_keyboard():
    keyboard = VkKeyboard(one_time=False)
    keyboard.add_button("▶️ Смотреть", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("📥 Скачать", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🔍 Новый поиск", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    return keyboard

def get_infinite_shorts_keyboard(can_prev=False):
    keyboard = VkKeyboard(one_time=False)
    
    if can_prev:
        keyboard.add_button("⬆️ Предыдущее", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("⬇️ Следующее", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("🎲 Случайное", color=VkKeyboardColor.PRIMARY)
    
    keyboard.add_line()
    keyboard.add_button("📊 Статистика", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("✏️ Сменить запрос", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard

def get_search_query_keyboard():
    keyboard = VkKeyboard(one_time=True)
    keyboard.add_button("🎲 Случайный запрос", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🏠 Главное меню", color=VkKeyboardColor.NEGATIVE)
    return keyboard

# ==================== ФУНКЦИИ YOUTUBE API ====================
def search_youtube_videos(query, max_results=10, page_token=None):
    """Поиск видео на YouTube"""
    try:
        request = youtube.search().list(
            part="snippet",
            q=query,
            maxResults=max_results,
            type="video",
            pageToken=page_token if page_token else "",
            regionCode="RU"
        )
        response = request.execute()
        
        videos = []
        for item in response.get("items", []):
            videos.append({
                "id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel": item["snippet"]["channelTitle"],
                "channel_id": item["snippet"]["channelId"],
                "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
            })
        
        return videos, response.get("nextPageToken")
    except HttpError as e:
        print(f"YouTube API ошибка: {e}")
        return [], None

def search_youtube_channels(query, max_results=10, page_token=None):
    """Поиск каналов на YouTube"""
    try:
        request = youtube.search().list(
            part="snippet",
            q=query,
            maxResults=max_results,
            type="channel",
            pageToken=page_token if page_token else "",
            regionCode="RU"
        )
        response = request.execute()
        
        channels = []
        for item in response.get("items", []):
            channels.append({
                "id": item["id"]["channelId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"][:100] if item["snippet"]["description"] else "",
                "url": f"https://www.youtube.com/channel/{item['id']['channelId']}"
            })
        
        return channels, response.get("nextPageToken")
    except HttpError as e:
        print(f"YouTube API ошибка: {e}")
        return [], None

def get_channel_videos(channel_id, max_results=20, page_token=None):
    """Получает видео с канала"""
    try:
        # Получаем плейлист с видео канала
        request = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        )
        response = request.execute()
        
        if not response.get("items"):
            return [], None
        
        uploads_playlist_id = response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        
        # Получаем видео из плейлиста
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results,
            pageToken=page_token if page_token else ""
        )
        response = request.execute()
        
        videos = []
        for item in response.get("items", []):
            videos.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": item["snippet"]["title"],
                "url": f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}"
            })
        
        return videos, response.get("nextPageToken")
    except HttpError as e:
        print(f"YouTube API ошибка: {e}")
        return [], None

def get_next_shorts(search_query=None, count=5):
    """Получает новые Shorts по русскому поисковому запросу"""
    all_shorts = []
    
    # Если запрос не указан, выбираем случайное русское слово
    if not search_query:
        search_query = random.choice(RUSSIAN_KEYWORDS)
    
    try:
        # Ищем Shorts по запросу
        request = youtube.search().list(
            part="snippet",
            q=search_query,
            maxResults=count + 5,
            type="video",
            videoDuration="short",
            regionCode="RU"
        )
        response = request.execute()
        
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            
            if not is_video_viewed(video_id):
                all_shorts.append({
                    "id": video_id,
                    "title": item["snippet"]["title"],
                    "channel": item["snippet"]["channelTitle"],
                    "url": f"https://www.youtube.com/shorts/{video_id}",
                    "search_query": search_query
                })
                
                if len(all_shorts) >= count:
                    return all_shorts, search_query
        
        # Если не хватило видео, добавляем еще из другого запроса
        if len(all_shorts) < count:
            backup_query = random.choice(RUSSIAN_KEYWORDS)
            request2 = youtube.search().list(
                part="snippet",
                q=backup_query,
                maxResults=count,
                type="video",
                videoDuration="short",
                regionCode="RU"
            )
            response2 = request2.execute()
            
            for item in response2.get("items", []):
                video_id = item["id"]["videoId"]
                if not is_video_viewed(video_id) and not any(v['id'] == video_id for v in all_shorts):
                    all_shorts.append({
                        "id": video_id,
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "url": f"https://www.youtube.com/shorts/{video_id}",
                        "search_query": backup_query
                    })
                    
                    if len(all_shorts) >= count:
                        return all_shorts, search_query
        
    except HttpError as e:
        print(f"YouTube API ошибка: {e}")
    
    return all_shorts, search_query

# ==================== ФУНКЦИИ ЗАГРУЗКИ ВИДЕО (yt-dlp) ====================
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
    """Скачивает видео в 720p с помощью yt-dlp"""
    try:
        ydl_opts = {
            'format': 'best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'merge_output_format': 'mp4',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Untitled')
            filename = ydl.prepare_filename(info)
            
            # Если расширение не mp4, меняем
            if not filename.endswith('.mp4'):
                base = os.path.splitext(filename)[0]
                filename = base + '.mp4'
            
            # Получаем качество
            resolution = "720p"
            for format in info.get('formats', []):
                if format.get('height') == 720:
                    resolution = f"{format.get('height')}p"
                    break
            
            return filename, title, resolution
        
    except Exception as e:
        print(f"Ошибка скачивания yt-dlp: {e}")
        return None, None, None

def upload_video_to_vk(video_file, title):
    try:
        save_data = vk_user.video.save(
            name=title[:100],
            description=f"Скачано с YouTube через FreeTube",
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

# ==================== ФУНКЦИИ ОТПРАВКИ СООБЩЕНИЙ ====================
def send_message(vk, user_id, message, attachment=None, keyboard=None):
    try:
        params = {
            "user_id": user_id,
            "message": message,
            "random_id": 0
        }
        if attachment:
            params["attachment"] = attachment
        if keyboard:
            params["keyboard"] = keyboard.get_keyboard()
        vk.messages.send(**params)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def send_search_results(user_id, query, results, current_start, search_type="video"):
    """Отправляет результаты поиска"""
    if not results:
        send_message(vk_group, user_id, "❌ Ничего не найдено", keyboard=get_main_keyboard())
        return
    
    if search_type == "video":
        message = f"🔍 Результаты поиска видео: **{query}**\n\n"
        for i, video in enumerate(results, start=1):
            message += f"{current_start + i}. 🎬 {video['title'][:60]}\n📺 {video['channel'][:30]}\n🔗 {video['url']}\n\n"
    else:
        message = f"🔍 Результаты поиска каналов: **{query}**\n\n"
        for i, channel in enumerate(results, start=1):
            message += f"{current_start + i}. 📺 **{channel['title']}**\n📝 {channel['description'][:50]}...\n🔗 {channel['url']}\n\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n\n⚠️ Слишком много результатов, урезано"
    
    keyboard = get_navigation_keyboard(current_start)
    send_message(vk_group, user_id, message, keyboard=keyboard)

def send_channel_videos(user_id, channel_name, videos, page_token=None, page=0):
    """Отправляет видео с канала"""
    if not videos:
        send_message(vk_group, user_id, "❌ На канале нет видео", keyboard=get_main_keyboard())
        return
    
    message = f"📺 **Видео канала: {channel_name}**\n\n"
    for i, video in enumerate(videos, start=1):
        message += f"{i}. 🎬 {video['title'][:70]}\n🔗 {video['url']}\n\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n\n⚠️ Урезано"
    
    keyboard = get_channel_videos_keyboard(page)
    send_message(vk_group, user_id, message, keyboard=keyboard)

def send_shorts_video(user_id, short, index=None, total=None):
    """Скачивает и отправляет Shorts видео"""
    
    if index is not None and total is not None:
        send_message(vk_group, user_id, f"📥 Скачиваю Shorts {index+1}/{total}: {short['title'][:50]}...")
    else:
        send_message(vk_group, user_id, f"📥 Скачиваю: {short['title'][:50]}...")
    
    file_path, title, quality = download_video_720p(short['url'])
    
    if not file_path or not os.path.exists(file_path):
        send_message(vk_group, user_id, f"❌ Не удалось скачать: {short['title'][:50]}")
        return False
    
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    
    if file_size > 1900:
        send_message(vk_group, user_id, f"⚠️ Видео слишком большое ({file_size:.0f}MB)\nВК не принимает файлы больше 2GB")
        os.remove(file_path)
        return False
    
    send_message(vk_group, user_id, f"📤 Загружаю в ВК ({file_size:.1f}MB)...")
    attachment = upload_video_to_vk(file_path, title)
    
    if attachment:
        search_query = short.get('search_query', '')
        add_viewed_video(short['id'], title, short['channel'], user_id, search_query)
        unique_vids, total_views = get_shorts_stats()
        
        message = f"📱 **YouTube Shorts**\n\n"
        message += f"🎬 {title[:100]}\n"
        message += f"📺 Канал: {short['channel']}\n"
        message += f"🎬 Качество: {quality}\n"
        message += f"🔍 Поисковый запрос: {search_query}\n"
        message += f"━━━━━━━━━━━━━━━━━━\n"
        message += f"📊 Статистика бота:\n"
        message += f"• Всего просмотров: {total_views}\n"
        message += f"• Уникальных видео: {unique_vids}\n"
        message += f"━━━━━━━━━━━━━━━━━━\n"
        message += f"💡 Нажмите ⬇️ Следующее для нового видео!"
        
        send_message(vk_group, user_id, message, attachment=attachment)
    else:
        send_message(vk_group, user_id, f"❌ Ошибка загрузки в ВК")
    
    time.sleep(2)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    return True

# ==================== ОСНОВНАЯ ЛОГИКА ====================
def process_message(user_id, text):
    """Обработка сообщений"""
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "state": "main", 
            "data": {
                "shorts_history": [],
                "current_position": -1,
                "current_search_query": None
            }
        }
    
    session = user_sessions[user_id]
    
    # Главное меню
    if text == "🏠 Главное меню":
        session["state"] = "main"
        session["data"]["shorts_history"] = []
        session["data"]["current_position"] = -1
        send_message(vk_group, user_id, "🏠 Главное меню FreeTube\nВыберите действие:", keyboard=get_main_keyboard())
        return
    
    # Обработка команд главного меню
    if session["state"] == "main":
        if text == "🔍 Поиск YouTube":
            session["state"] = "select_search_type"
            send_message(vk_group, user_id, "🔍 Что вы хотите найти?", keyboard=get_search_type_keyboard())
        
        elif text == "📱 FreeShorts":
            session["state"] = "waiting_shorts_query"
            send_message(vk_group, user_id, "🔍 Введите поисковый запрос на русском языке\n(например: приколы, котики, музыка, спорт)\n\nИли нажмите 'Случайный запрос'", keyboard=get_search_query_keyboard())
        
        elif text == "❓ Помощь":
            help_text = """🎬 **FreeTube - Бесконечные Shorts + Поиск видео**

📌 **Возможности:**
• 🔍 Поиск видео и каналов
• 📱 Бесконечная лента Shorts по русским запросам
• 🎲 Случайное видео
• 📥 Скачивание любых видео
• 📺 Просмотр видео с каналов

🔍 **Русские запросы для Shorts:**
Приколы, котики, музыка, спорт, танцы, животные, 
лайфхаки, рецепты, путешествия, мемы и любые другие!

💾 **Особенности:**
• Видео НИКОГДА не повторяются!
• Бесконечная генерация контента
• Работает при блокировке YouTube

⚡ Просто введите любой русский запрос и наслаждайтесь!"""
            send_message(vk_group, user_id, help_text, keyboard=get_main_keyboard())
        
        elif text == "ℹ️ О боте":
            unique_vids, total_views = get_shorts_stats()
            about = f"""🤖 **FreeTube v6.0 - Infinite Shorts + Поиск**

🇷🇺 Свободный YouTube в ВК
🔍 Поиск по русским запросам
🔄 Бесконечная лента Shorts
📺 Поиск и просмотр каналов
📥 Скачивание видео в 720p

📊 **Статистика бота:**
• Просмотрено видео: {total_views}
• Уникальных Shorts: {unique_vids}
• Активных пользователей: {len(user_sessions)}

💡 **Новое:** Поиск Shorts по русским словам!

✅ Статус: Работает"""
            send_message(vk_group, user_id, about, keyboard=get_main_keyboard())
        
        elif text.startswith("http") and ("youtube.com" in text or "youtu.be" in text):
            handle_video_request(user_id, text)
        
        else:
            send_message(vk_group, user_id, "Пожалуйста, используйте кнопки меню", keyboard=get_main_keyboard())
    
    # Выбор типа поиска
    elif session["state"] == "select_search_type":
        if text == "🎬 Видео":
            session["state"] = "waiting_search_video"
            send_message(vk_group, user_id, "🔍 Введите поисковый запрос для видео:", keyboard=get_main_keyboard())
        elif text == "📺 Каналы":
            session["state"] = "waiting_search_channel"
            send_message(vk_group, user_id, "🔍 Введите название канала для поиска:", keyboard=get_main_keyboard())
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())
        else:
            send_message(vk_group, user_id, "Пожалуйста, выберите тип поиска", keyboard=get_search_type_keyboard())
    
    # Ожидание запроса для Shorts
    elif session["state"] == "waiting_shorts_query":
        if text == "🎲 Случайный запрос":
            search_query = random.choice(RUSSIAN_KEYWORDS)
            session["state"] = "infinite_shorts"
            session["data"]["shorts_history"] = []
            session["data"]["current_position"] = -1
            session["data"]["current_search_query"] = search_query
            
            send_message(vk_group, user_id, f"🎬 Запускаю БЕСКОНЕЧНУЮ ленту Shorts по запросу: **{search_query}**!\n\n⚡ Нажимайте ⬇️ Следующее для новых видео. Видео НЕ повторяются!")
            load_next_shorts(user_id)
        
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())
        
        elif text and len(text) > 1:
            search_query = text
            session["state"] = "infinite_shorts"
            session["data"]["shorts_history"] = []
            session["data"]["current_position"] = -1
            session["data"]["current_search_query"] = search_query
            
            send_message(vk_group, user_id, f"🎬 Запускаю БЕСКОНЕЧНУЮ ленту Shorts по запросу: **{search_query}**!\n\n⚡ Нажимайте ⬇️ Следующее для новых видео. Видео НЕ повторяются!")
            load_next_shorts(user_id)
        
        else:
            send_message(vk_group, user_id, "❌ Введите поисковый запрос (минимум 2 символа)", keyboard=get_search_query_keyboard())
    
    # Поиск видео
    elif session["state"] == "waiting_search_video":
        if text and len(text) > 2:
            session["state"] = "search_results_video"
            session["data"]["search_query"] = text
            session["data"]["search_start"] = 0
            session["data"]["search_type"] = "video"
            
            results, _ = search_youtube_videos(text, max_results=10)
            session["data"]["search_results"] = results
            
            send_search_results(user_id, text, results, 0, "video")
        else:
            send_message(vk_group, user_id, "❌ Введите поисковый запрос (минимум 3 символа)", keyboard=get_main_keyboard())
    
    # Поиск каналов
    elif session["state"] == "waiting_search_channel":
        if text and len(text) > 2:
            session["state"] = "search_results_channel"
            session["data"]["search_query"] = text
            session["data"]["search_start"] = 0
            session["data"]["search_type"] = "channel"
            
            results, _ = search_youtube_channels(text, max_results=10)
            session["data"]["search_results"] = results
            
            send_search_results(user_id, text, results, 0, "channel")
        else:
            send_message(vk_group, user_id, "❌ Введите название канала (минимум 3 символа)", keyboard=get_main_keyboard())
    
    # Навигация по результатам поиска
    elif session["state"] in ["search_results_video", "search_results_channel"]:
        if text == "⬆️ Вверх" and session["data"]["search_start"] >= 10:
            session["data"]["search_start"] -= 10
            results = session["data"]["search_results"]
            send_search_results(user_id, session["data"]["search_query"], results, session["data"]["search_start"], session["data"]["search_type"])
        
        elif text == "⬇️ Вниз":
            session["data"]["search_start"] += 10
            if session["data"]["search_type"] == "video":
                results, _ = search_youtube_videos(session["data"]["search_query"], max_results=10)
            else:
                results, _ = search_youtube_channels(session["data"]["search_query"], max_results=10)
            session["data"]["search_results"] = results
            send_search_results(user_id, session["data"]["search_query"], results, session["data"]["search_start"], session["data"]["search_type"])
        
        elif text == "🔍 Новый поиск":
            session["state"] = "select_search_type"
            send_message(vk_group, user_id, "🔍 Что вы хотите найти?", keyboard=get_search_type_keyboard())
        
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())
        
        elif text.isdigit():
            item_num = int(text)
            if 1 <= item_num <= len(session["data"]["search_results"]):
                item = session["data"]["search_results"][item_num - 1]
                
                if session["data"]["search_type"] == "video":
                    # Выбрано видео
                    session["state"] = "video_selected"
                    session["data"]["selected_video"] = item
                    send_message(vk_group, user_id, f"🎬 {item['title']}\n\nВыберите действие:", keyboard=get_video_control_keyboard())
                else:
                    # Выбран канал
                    channel = item
                    session["state"] = "viewing_channel"
                    session["data"]["current_channel"] = channel
                    session["data"]["channel_videos_page"] = 0
                    session["data"]["channel_videos_token"] = None
                    
                    send_message(vk_group, user_id, f"📺 Загружаю видео с канала **{channel['title']}**...")
                    videos, next_token = get_channel_videos(channel['id'], max_results=10)
                    session["data"]["channel_videos"] = videos
                    session["data"]["channel_videos_next_token"] = next_token
                    
                    send_channel_videos(user_id, channel['title'], videos, page=0)
            else:
                send_message(vk_group, user_id, f"❌ Введите номер от 1 до {len(session['data']['search_results'])}")
    
    # Просмотр видео канала
    elif session["state"] == "viewing_channel":
        if text == "⬇️ Следующие видео":
            session["data"]["channel_videos_page"] += 1
            channel = session["data"]["current_channel"]
            videos, next_token = get_channel_videos(channel['id'], max_results=10, page_token=session["data"].get("channel_videos_next_token"))
            if videos:
                session["data"]["channel_videos"] = videos
                session["data"]["channel_videos_next_token"] = next_token
                send_channel_videos(user_id, channel['title'], videos, page=session["data"]["channel_videos_page"])
            else:
                send_message(vk_group, user_id, "❌ Больше видео нет")
        
        elif text == "⬆️ Предыдущие видео" and session["data"]["channel_videos_page"] > 0:
            send_message(vk_group, user_id, "⚠️ К сожалению, вернуться к предыдущим видео нельзя из-за ограничений YouTube API")
        
        elif text == "🔍 Новый поиск":
            session["state"] = "select_search_type"
            send_message(vk_group, user_id, "🔍 Что вы хотите найти?", keyboard=get_search_type_keyboard())
        
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())
        
        elif text.isdigit():
            video_num = int(text)
            if 1 <= video_num <= len(session["data"]["channel_videos"]):
                video = session["data"]["channel_videos"][video_num - 1]
                session["state"] = "video_selected"
                session["data"]["selected_video"] = video
                send_message(vk_group, user_id, f"🎬 {video['title']}\n\nВыберите действие:", keyboard=get_video_control_keyboard())
            else:
                send_message(vk_group, user_id, f"❌ Введите номер от 1 до {len(session['data']['channel_videos'])}")
    
    # Бесконечная лента Shorts
    elif session["state"] == "infinite_shorts":
        if text == "⬇️ Следующее":
            load_next_shorts(user_id)
        
        elif text == "⬆️ Предыдущее" and session["data"]["current_position"] > 0:
            session["data"]["current_position"] -= 1
            prev_short = session["data"]["shorts_history"][session["data"]["current_position"]]
            keyboard = get_infinite_shorts_keyboard(can_prev=session["data"]["current_position"] > 0)
            send_message(vk_group, user_id, "🔄 Загружаю предыдущее видео...")
            send_shorts_video(user_id, prev_short)
            send_message(vk_group, user_id, f"📱 Видео {session['data']['current_position'] + 1} в истории\n\nПродолжайте просмотр!", keyboard=keyboard)
        
        elif text == "🎲 Случайное":
            send_message(vk_group, user_id, "🎲 Ищу случайное видео...")
            random_shorts, _ = get_next_shorts(session["data"].get("current_search_query"), count=3)
            if random_shorts:
                for short in random_shorts:
                    if not any(s['id'] == short['id'] for s in session["data"]["shorts_history"]):
                        session["data"]["shorts_history"].append(short)
                        session["data"]["current_position"] = len(session["data"]["shorts_history"]) - 1
                        keyboard = get_infinite_shorts_keyboard(can_prev=True)
                        send_shorts_video(user_id, short)
                        send_message(vk_group, user_id, f"🎲 Случайное видео #{session['data']['current_position'] + 1}\n\nНаслаждайтесь!", keyboard=keyboard)
                        break
        
        elif text == "📊 Статистика":
            unique_vids, total_views = get_shorts_stats()
            stats_msg = f"📊 **Статистика бесконечной ленты**\n\n"
            stats_msg += f"🎬 Посмотрено в этой сессии: {len(session['data']['shorts_history'])}\n"
            stats_msg += f"🔍 Текущий запрос: {session['data'].get('current_search_query', 'Не указан')}\n"
            stats_msg += f"━━━━━━━━━━━━━━━━━━\n"
            stats_msg += f"📊 Глобальная статистика:\n"
            stats_msg += f"• Уникальных видео: {unique_vids}\n"
            stats_msg += f"• Всего просмотров: {total_views}\n"
            stats_msg += f"━━━━━━━━━━━━━━━━━━\n"
            stats_msg += f"💡 Видео никогда не повторяются!"
            send_message(vk_group, user_id, stats_msg)
        
        elif text == "✏️ Сменить запрос":
            session["state"] = "waiting_shorts_query"
            send_message(vk_group, user_id, "🔍 Введите новый поисковый запрос на русском языке:", keyboard=get_search_query_keyboard())
        
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            session["data"]["shorts_history"] = []
            session["data"]["current_position"] = -1
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())
    
    # Режим выбора действия с видео
    elif session["state"] == "video_selected":
        if text == "▶️ Смотреть":
            video = session["data"]["selected_video"]
            send_message(vk_group, user_id, f"🎬 {video['title']}\n\n🔗 Ссылка для просмотра:\n{video['url']}", keyboard=get_main_keyboard())
        
        elif text == "📥 Скачать":
            video = session["data"]["selected_video"]
            handle_video_request(user_id, video["url"], from_menu=False)
        
        elif text == "🏠 Главное меню":
            session["state"] = "main"
            send_message(vk_group, user_id, "🏠 Главное меню", keyboard=get_main_keyboard())

def load_next_shorts(user_id):
    """Загружает следующее Shorts для бесконечной ленты"""
    session = user_sessions[user_id]
    
    if session["data"]["current_position"] + 1 < len(session["data"]["shorts_history"]):
        session["data"]["current_position"] += 1
        short = session["data"]["shorts_history"][session["data"]["current_position"]]
        keyboard = get_infinite_shorts_keyboard(can_prev=session["data"]["current_position"] > 0)
        send_message(vk_group, user_id, "📱 Загружаю следующее видео...")
        send_shorts_video(user_id, short)
        send_message(vk_group, user_id, f"📱 Видео {session['data']['current_position'] + 1} в истории\n\nПродолжайте просмотр!", keyboard=keyboard)
    else:
        send_message(vk_group, user_id, "🔍 Ищу новые видео...")
        search_query = session["data"].get("current_search_query", random.choice(RUSSIAN_KEYWORDS))
        new_shorts, used_query = get_next_shorts(search_query, count=3)
        
        if new_shorts:
            for short in new_shorts:
                if not any(s['id'] == short['id'] for s in session["data"]["shorts_history"]):
                    short['search_query'] = used_query
                    session["data"]["shorts_history"].append(short)
            
            if session["data"]["current_position"] + 1 < len(session["data"]["shorts_history"]):
                session["data"]["current_position"] += 1
                short = session["data"]["shorts_history"][session["data"]["current_position"]]
                keyboard = get_infinite_shorts_keyboard(can_prev=session["data"]["current_position"] > 0)
                send_shorts_video(user_id, short)
                send_message(vk_group, user_id, f"📱 Новое видео #{session['data']['current_position'] + 1}!\n\nПродолжайте просмотр!", keyboard=keyboard)
            else:
                send_message(vk_group, user_id, "❌ Не удалось найти новые видео. Попробуйте сменить запрос или повторить позже.", keyboard=get_infinite_shorts_keyboard(can_prev=True))
        else:
            send_message(vk_group, user_id, "❌ Не удалось найти новые видео. Попробуйте сменить запрос.", keyboard=get_infinite_shorts_keyboard(can_prev=True))

def handle_video_request(user_id, url, from_menu=True):
    """Обрабатывает запрос на скачивание видео"""
    send_message(vk_group, user_id, "📥 Скачиваю видео... Это может занять некоторое время")
    
    file_path, title, quality = download_video_720p(url)
    
    if not file_path or not os.path.exists(file_path):
        send_message(vk_group, user_id, "❌ Ошибка скачивания видео. Возможно, видео недоступно или слишком длинное", 
                    keyboard=get_main_keyboard() if from_menu else None)
        return
    
    file_size = os.path.getsize(file_path) / (1024 * 1024)
    
    if file_size > 1900:
        send_message(vk_group, user_id, f"⚠️ Видео слишком большое ({file_size:.0f}MB)\nВК не принимает файлы больше 2GB",
                    keyboard=get_main_keyboard() if from_menu else None)
        os.remove(file_path)
        return
    
    send_message(vk_group, user_id, f"📤 Загружаю {file_size:.1f}MB в ВК...")
    
    attachment = upload_video_to_vk(file_path, title)
    
    if attachment:
        send_message(vk_group, user_id, f"✅ **{title[:50]}**\nКачество: {quality}\n\nВидео готово к просмотру!", 
                    attachment=attachment, keyboard=get_main_keyboard() if from_menu else None)
    else:
        send_message(vk_group, user_id, "❌ Ошибка загрузки в ВК. Попробуйте позже",
                    keyboard=get_main_keyboard() if from_menu else None)
    
    time.sleep(2)
    if os.path.exists(file_path):
        os.remove(file_path)

# ==================== ЗАПУСК БОТА ====================
print("=" * 60)
print("🎬 FreeTube - БЕСКОНЕЧНЫЕ Shorts + Поиск по русским запросам")
print("📁 Папка загрузок: downloads")
print("🔍 Поиск: русские слова и фразы")
print("♾️ Режим: Бесконечная лента (видео НЕ повторяются)")
print("📺 Новое: Поиск Shorts по любым русским словам!")
print("💾 База данных просмотренных видео активна")
print("🎨 Бот готов к работе!")
print("=" * 60)

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW and event.to_me:
        user_id = event.user_id
        text = event.text.strip()
        
        print(f"\n📨 От {user_id}: {text[:50]}")
        process_message(user_id, text)