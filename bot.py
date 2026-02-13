import asyncio
import logging
import pytz
import os

from telegram import Bot, Poll, Update
from telegram.error import TelegramError
from telegram.ext import Application, MessageHandler, filters, ContextTypes, ChatMemberHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ НАСТРОЙКИ ============
TOKEN = "8458423184:AAGRqzCZyysNc62oudYC8TX7CNMqraRKTW4"  # Ваш токен
TIMEZONE = "Europe/Moscow"  # Часовой пояс
SEND_HOUR = 15      # Час отправки
SEND_MINUTE = 50    # Минута отправки
TEXT_TEMPLATE = "Прошу выполнить от 10 заданий № {} из РешуОГЭ(ЕГЭ) сегодня и прислать скриншот"
MAX_NUMBER = 16     # Максимальный номер задания
# ===================================

# Файл для хранения списка чатов (групп)
CHATS_FILE = "chats.txt"
# Файл для хранения текущего номера задания (один на всех, так и задумано)
STATE_FILE = "counter.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Работа со списком чатов ----------
def load_chats():
    """Загружает множество chat_id из файла."""
    if not os.path.exists(CHATS_FILE):
        return set()
    with open(CHATS_FILE, "r") as f:
        return {int(line.strip()) for line in f if line.strip()}

def save_chats(chats):
    """Сохраняет множество chat_id в файл."""
    with open(CHATS_FILE, "w") as f:
        for chat_id in chats:
            f.write(f"{chat_id}\n")

def add_chat(chat_id):
    """Добавляет chat_id в файл, если его там нет."""
    chats = load_chats()
    if chat_id not in chats:
        chats.add(chat_id)
        save_chats(chats)
        logger.info(f"Добавлен новый чат: {chat_id}")

def remove_chat(chat_id):
    """Удаляет chat_id из файла."""
    chats = load_chats()
    if chat_id in chats:
        chats.discard(chat_id)
        save_chats(chats)
        logger.info(f"Чат удалён: {chat_id}")

# ---------- Работа со счётчиком заданий ----------
def read_counter():
    """Читает текущий номер задания из файла. Если файла нет - создаёт с 1."""
    try:
        with open(STATE_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        with open(STATE_FILE, "w") as f:
            f.write("1")
        return 1

def write_counter(value):
    """Записывает номер задания в файл."""
    with open(STATE_FILE, "w") as f:
        f.write(str(value))

# ---------- Отправка сообщения и опроса ----------
async def send_daily_task(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение и опрос во все сохранённые чаты."""
    task_num = read_counter()
    chats = load_chats()
    if not chats:
        logger.warning("Нет сохранённых чатов для рассылки.")
        return

    for chat_id in chats:
        try:
            # 1. Текстовое напоминание
            message = TEXT_TEMPLATE.format(task_num)
            await context.bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"Сообщение отправлено в чат {chat_id}")

            # 2. Опрос
            question = f"Задание № {task_num}: твой прогресс?"
            options = ["Сделал", "В процессе", "Не успеваю сделать сегодня"]
            await context.bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=options,
                is_anonymous=False,
                allows_multiple_answers=False,
                type=Poll.REGULAR
            )
            logger.info(f"Опрос отправлен в чат {chat_id}")
        except TelegramError as e:
            logger.error(f"Ошибка при отправке в чат {chat_id}: {e}")
            # Если бот больше не в чате (например, удалили) — удаляем чат из списка
            if "Forbidden" in str(e) or "chat not found" in str(e):
                remove_chat(chat_id)
        except Exception as e:
            logger.error(f"Неизвестная ошибка для чата {chat_id}: {e}")

    # Обновляем счётчик после отправки во все чаты
    next_num = task_num + 1
    if next_num > MAX_NUMBER:
        next_num = 1
    write_counter(next_num)
    logger.info(f"Следующий номер задания: {next_num}")

# ---------- Обработчики событий ----------
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отслеживает сообщения в группах и добавляет chat_id в список."""
    chat = update.effective_chat
    # Нас интересуют только группы (chat_id < 0)
    if chat and chat.id < 0:
        add_chat(chat.id)

async def track_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отслеживает добавление/удаление бота в группах."""
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    # Проверяем, что это группа
    if chat.type not in ["group", "supergroup"]:
        return

    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status

    # Если бота добавили или повысили до администратора
    if new_status in ["member", "administrator"] and old_status in ["left", "kicked"]:
        add_chat(chat.id)
    # Если бота удалили или заблокировали
    elif new_status in ["left", "kicked"] and old_status in ["member", "administrator"]:
        remove_chat(chat.id)

# ---------- Запуск бота ----------
def main():
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    # 1. На любое сообщение в группе (для добавления в список, если вдруг не сработал my_chat_member)
    application.add_handler(MessageHandler(filters.ChatType.GROUPS, track_chats))
    # 2. На изменение статуса бота в чате
    application.add_handler(ChatMemberHandler(track_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # Настраиваем планировщик внутри приложения (JobQueue)
    job_queue = application.job_queue
    if job_queue:
        # Запускаем задачу ежедневно в указанное время
        job_queue.run_daily(
            send_daily_task,
            time=pytz.timezone(TIMEZONE).localize(datetime.time(hour=SEND_HOUR, minute=SEND_MINUTE)),
            name="daily_reminder"
        )
        logger.info(f"Запланирована ежедневная отправка в {SEND_HOUR:02d}:{SEND_MINUTE:02d} {TIMEZONE}")
    else:
        logger.error("JobQueue не доступна. Убедитесь, что установлены зависимости.")

    # Запускаем бота
    logger.info("Бот запущен и ожидает события...")
    application.run_polling()

if __name__ == "__main__":
    main()