import asyncio
import logging
import pytz
import os
import json

from telegram import Bot, Poll, Update
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters, ContextTypes, ChatMemberHandler, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ НАСТРОЙКИ ============
TOKEN = "8458423184:AAGRqzCZyysNc62oudYC8TX7CNMqraRKTW4"
TIMEZONE = "Europe/Moscow"
SEND_HOUR = 02
SEND_MINUTE = 00
TEXT_TEMPLATE = "Прошу выполнить от 10 заданий № {} из РешуОГЭ(ЕГЭ) сегодня и прислать скриншот"
MAX_NUMBER = 16
# Список ID групп, которые будут добавлены при первом запуске (можно дополнять)
INITIAL_CHAT_IDS = [
    -4664223461,
    -1003711276284,
    -1002995593987,
    -1003705629246,
    -4964425544,
    -1003811911983
]
# ===================================

CHATS_FILE = "chats.txt"
COUNTERS_FILE = "counters.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Работа со списком чатов ----------
def load_chats():
    if not os.path.exists(CHATS_FILE):
        chats = set(INITIAL_CHAT_IDS)
        save_chats(chats)
        return chats
    with open(CHATS_FILE, "r") as f:
        return {int(line.strip()) for line in f if line.strip()}

def save_chats(chats):
    with open(CHATS_FILE, "w") as f:
        for chat_id in sorted(chats):
            f.write(f"{chat_id}\n")

def add_chat(chat_id):
    chats = load_chats()
    if chat_id not in chats:
        chats.add(chat_id)
        save_chats(chats)
        set_counter(chat_id, 1)  # новому чату – первый номер
        logger.info(f"Добавлен новый чат: {chat_id}")

def remove_chat(chat_id):
    chats = load_chats()
    if chat_id in chats:
        chats.discard(chat_id)
        save_chats(chats)
        remove_counter(chat_id)
        logger.info(f"Чат удалён: {chat_id}")

# ---------- Работа со счётчиками (JSON) ----------
def load_counters():
    if not os.path.exists(COUNTERS_FILE):
        return {}
    with open(COUNTERS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_counters(counters):
    with open(COUNTERS_FILE, "w") as f:
        json.dump(counters, f, indent=2)

def get_counter(chat_id):
    counters = load_counters()
    if str(chat_id) not in counters:
        counters[str(chat_id)] = 1
        save_counters(counters)
    return counters[str(chat_id)]

def set_counter(chat_id, value):
    counters = load_counters()
    counters[str(chat_id)] = value
    save_counters(counters)

def increment_counter(chat_id):
    current = get_counter(chat_id)
    next_val = current + 1
    if next_val > MAX_NUMBER:
        next_val = 1
    set_counter(chat_id, next_val)
    return next_val

def remove_counter(chat_id):
    counters = load_counters()
    if str(chat_id) in counters:
        del counters[str(chat_id)]
        save_counters(counters)

# ---------- Команда /set_task ----------
async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("Эта команда работает только в группах.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Пожалуйста, укажите номер задания. Пример: /set_task 5")
        return
    try:
        new_num = int(args[0])
        if new_num < 1 or new_num > MAX_NUMBER:
            await update.message.reply_text(f"Номер должен быть от 1 до {MAX_NUMBER}.")
            return
    except ValueError:
        await update.message.reply_text("Некорректный номер. Введите число.")
        return

    chat_id = chat.id
    set_counter(chat_id, new_num)
    await update.message.reply_text(f"✅ Текущий номер задания для этой группы установлен на {new_num}.")

# ---------- Ежедневная отправка ----------
async def send_daily_task():
    chats = load_chats()
    if not chats:
        logger.warning("Нет чатов для рассылки.")
        return

    bot = Bot(token=TOKEN)
    for chat_id in chats:
        try:
            task_num = get_counter(chat_id)

            # Текстовое напоминание
            message = TEXT_TEMPLATE.format(task_num)
            await bot.send_message(chat_id=chat_id, text=message)

            # Опрос
            question = f"Задание № {task_num}: твой прогресс?"
            options = ["Сделал", "В процессе", "Не успеваю сделать сегодня"]
            await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False,
                type=Poll.REGULAR
            )
            logger.info(f"Отправлено в чат {chat_id} (задание {task_num})")

            # Увеличиваем счётчик для этого чата
            increment_counter(chat_id)

        except TelegramError as e:
            logger.error(f"Ошибка в чате {chat_id}: {e}")
            if "Forbidden" in str(e) or "chat not found" in str(e):
                remove_chat(chat_id)
        except Exception as e:
            logger.error(f"Неизвестная ошибка для чата {chat_id}: {e}")

# ---------- Отслеживание добавления/удаления бота ----------
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat and chat.id < 0:
        add_chat(chat.id)

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    if chat.type not in ["group", "supergroup"]:
        return
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    if new_status in ["member", "administrator"] and old_status in ["left", "kicked"]:
        add_chat(chat.id)
    elif new_status in ["left", "kicked"] and old_status in ["member", "administrator"]:
        remove_chat(chat.id)

# ---------- Запуск ----------
async def main():
    # Инициализация файлов при первом запуске
    load_chats()
    load_counters()

    # Планировщик
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(
        send_daily_task,
        trigger=CronTrigger(hour=SEND_HOUR, minute=SEND_MINUTE, timezone=pytz.timezone(TIMEZONE))
    )
    scheduler.start()
    logger.info(f"Планировщик запущен, ежедневная отправка в {SEND_HOUR:02d}:{SEND_MINUTE:02d} {TIMEZONE}")

    # Запуск бота (обработка команд и событий)
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("set_task", set_task))
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, track_chats))
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    await application.initialize()
    await application.start()
    logger.info("Бот запущен, ожидание команд...")

    # Бесконечное ожидание
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()
        await application.stop()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())
