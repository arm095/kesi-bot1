import telebot
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import time
import threading
import schedule
import os
from flask import Flask

# ========== НАСТРОЙКИ ==========
TOKEN = os.environ.get("TOKEN")
GROUP = "ДЮ-9-2025"
# ==============================

if not TOKEN:
    print("Ошибка: не указан TOKEN")
    exit(1)

bot = telebot.TeleBot(TOKEN)
user_chat_ids = set()
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def get_schedule():
    url = "https://college-edu.ru/stud/raspisanie/"
    try:
        r = requests.get(url, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return None, f"Ошибка загрузки сайта: {e}"

    group_h2 = None
    for h2 in soup.find_all("h2"):
        if GROUP in h2.get_text():
            group_h2 = h2
            break
    if not group_h2:
        return None, "Группа не найдена на сайте"

    schedule_dict = {}
    for div in group_h2.find_next_siblings("div"):
        lines = [l.strip() for l in div.get_text("\n", strip=True).split("\n") if l.strip()]
        if not lines:
            continue
        day = lines[0]
        pairs = []
        i = 1
        while i < len(lines):
            if re.match(r"^\d+$", lines[i]):
                pair_num = lines[i]
                time_str = lines[i+1] if i+1 < len(lines) else ""
                subject = lines[i+2] if i+2 < len(lines) else ""
                teacher = lines[i+3] if i+3 < len(lines) else ""
                room = ""
                next_idx = i + 4
                if next_idx < len(lines) and ("ауд" in lines[next_idx].lower() or "сдо" in lines[next_idx].lower()):
                    room = lines[next_idx]
                    i = next_idx + 1
                else:
                    i = next_idx
                pairs.append({
                    "num": pair_num,
                    "time": time_str,
                    "subject": subject,
                    "teacher": teacher,
                    "room": room
                })
            else:
                i += 1
        schedule_dict[day] = pairs
    return schedule_dict, group_h2.get_text(strip=True)

def format_day(day_name, pairs):
    if not pairs:
        return f"<b>{day_name}</b>\nПар нет 🎉"
    text = f"<b>{day_name}</b>\n\n"
    for p in pairs:
        room = f" | {p['room']}" if p['room'] else ""
        text += f"<b>{p['num']} пара</b> ({p['time']})\n"
        text += f"{p['subject']}\n"
        text += f"{p['teacher']}{room}\n\n"
    return text.strip()

def get_day_schedule(target="today"):
    sched, group_name = get_schedule()
    if sched is None:
        return group_name

    today = datetime.now().date()
    target_date = today + timedelta(days=1) if target == "tomorrow" else today
    target_str = target_date.strftime("%d.%m.%y")

    for day_key, pairs in sched.items():
        if target_str in day_key:
            title = "Сегодня" if target == "today" else "Завтра"
            return f"📅 <b>{title}</b> ({day_key})\nГруппа: {group_name}\n\n" + format_day(day_key, pairs)

    return f"На {'сегодня' if target == 'today' else 'завтра'} пар в расписании не найдено."

@bot.message_handler(commands=['start', 'help'])
def start(message):
    user_chat_ids.add(message.chat.id)
    text = (
        "Привет! Я бот с расписанием колледжа КЭСИ 📚\n\n"
        "Команды:\n"
        "/сегодня — расписание на сегодня\n"
        "/завтра — расписание на завтра\n\n"
        "Или просто напиши «сегодня» / «завтра».\n\n"
        "Каждый вечер я буду сам присылать расписание на завтра."
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['сегодня', 'today'])
def today_cmd(message):
    user_chat_ids.add(message.chat.id)
    bot.reply_to(message, "Секунду, смотрю расписание...")
    result = get_day_schedule("today")
    bot.send_message(message.chat.id, result, parse_mode="HTML")

@bot.message_handler(commands=['завтра', 'tomorrow'])
def tomorrow_cmd(message):
    user_chat_ids.add(message.chat.id)
    bot.reply_to(message, "Секунду, смотрю расписание...")
    result = get_day_schedule("tomorrow")
    bot.send_message(message.chat.id, result, parse_mode="HTML")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["сегодня", "today"])
def today_text(message):
    today_cmd(message)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["завтра", "tomorrow"])
def tomorrow_text(message):
    tomorrow_cmd(message)

def send_daily():
    if not user_chat_ids:
        return
    result = get_day_schedule("tomorrow")
    for chat_id in list(user_chat_ids):
        try:
            bot.send_message(chat_id, "🔔 Расписание на завтра:\n\n" + result, parse_mode="HTML")
        except Exception:
            user_chat_ids.discard(chat_id)

def run_scheduler():
    schedule.every().day.at("20:00").do(send_daily)
    while True:
        schedule.run_pending()
        time.sleep(30)

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
