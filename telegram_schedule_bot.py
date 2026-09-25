#!/usr/bin/env python3
"""
Telegram бот для мониторинга расписания NATK
Отправляет уведомления при изменениях в расписании
"""

import os
import json
import requests
import schedule
import time
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Bot
from telegram.error import TelegramError
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы
TELEGRAM_TOKEN = "8855211514:AAGCLeRUJjK0uyL_gr1mYDipna8hR3A7gEs"
CHAT_ID = None  # Будет установлен при первом сообщении
NATK_URL = "https://natk.ru/stud-grad/schedule/187?gid=368"
GROUP_NAME = "РЭУ 26-256"
SCHEDULE_FILE = "schedule_cache.json"

# Инициализируем бота
bot = Bot(token=TELEGRAM_TOKEN)

def get_schedule_from_natk():
    """Получает расписание со страницы NATK"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(NATK_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            logger.error(f"Ошибка при загрузке страницы: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем таблицу с расписанием
        schedule_data = {}
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    # Проверяем если это заголовок дня
                    date_cell = cells[0].get_text(strip=True)
                    
                    if 'сентября' in date_cell or 'октября' in date_cell or \
                       'ноября' in date_cell or 'декабря' in date_cell:
                        current_date = date_cell
                        schedule_data[current_date] = []
                    elif current_date and len(cells[0].get_text(strip=True)) <= 2:
                        # Это пара
                        time_text = cells[0].get_text(strip=True)
                        lesson_text = cells[1].get_text(strip=True)
                        
                        schedule_data[current_date].append({
                            'время': time_text,
                            'предмет': lesson_text
                        })
        
        return schedule_data if schedule_data else None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к NATK: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при парсинге расписания: {e}")
        return None

def save_schedule(schedule_data):
    """Сохраняет расписание в файл"""
    try:
        with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=2)
        logger.info("Расписание сохранено")
    except Exception as e:
        logger.error(f"Ошибка при сохранении расписания: {e}")

def load_schedule():
    """Загружает сохраненное расписание из файла"""
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка при загрузке сохраненного расписания: {e}")
    return None

def compare_schedules(old_schedule, new_schedule):
    """Сравнивает два расписания и возвращает изменения"""
    if not old_schedule:
        return {"статус": "новое", "изменения": []}
    
    changes = []
    
    # Проверяем удаленные дни
    for date in old_schedule:
        if date not in new_schedule:
            changes.append(f"❌ Отменено: {date}")
    
    # Проверяем новые и измененные дни
    for date in new_schedule:
        if date not in old_schedule:
            changes.append(f"✅ Добавлено: {date}")
        else:
            # Сравниваем пары на этот день
            old_lessons = old_schedule[date]
            new_lessons = new_schedule[date]
            
            if old_lessons != new_lessons:
                changes.append(f"📝 Изменено: {date}")
                
                # Детально показываем что изменилось
                if len(new_lessons) < len(old_lessons):
                    changes.append(f"   ➖ Удалено {len(old_lessons) - len(new_lessons)} пар")
                elif len(new_lessons) > len(old_lessons):
                    changes.append(f"   ➕ Добавлено {len(new_lessons) - len(old_lessons)} пар")
    
    return {
        "статус": "изменено" if changes else "без изменений",
        "изменения": changes
    }

def send_notification(title, message):
    """Отправляет уведомление в Telegram"""
    global CHAT_ID
    
    if not CHAT_ID:
        logger.warning("CHAT_ID не установлен. Сообщение не отправлено.")
        return False
    
    try:
        full_message = f"<b>{title}</b>\n\n{message}"
        bot.send_message(
            chat_id=CHAT_ID,
            text=full_message,
            parse_mode='HTML'
        )
        logger.info(f"Сообщение отправлено: {title}")
        return True
    except TelegramError as e:
        logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
        return False

def check_schedule():
    """Проверяет расписание на изменения"""
    logger.info("Проверка расписания...")
    
    # Получаем новое расписание
    new_schedule = get_schedule_from_natk()
    
    if not new_schedule:
        send_notification(
            "⚠️ Ошибка при проверке расписания",
            "Не удалось загрузить расписание со страницы NATK.\n"
            "Проверьте интернет соединение и попробуйте позже."
        )
        return
    
    # Загружаем старое расписание
    old_schedule = load_schedule()
    
    # Сравниваем
    comparison = compare_schedules(old_schedule, new_schedule)
    
    # Если есть изменения, отправляем уведомление
    if comparison["изменения"]:
        message = f"Группа: <b>{GROUP_NAME}</b>\n\n"
        message += "\n".join(comparison["изменения"])
        message += f"\n\n🔗 <a href='{NATK_URL}'>Посмотреть полное расписание</a>"
        
        send_notification("📋 Изменения в расписании!", message)
    else:
        logger.info("Изменений в расписании не найдено")
    
    # Сохраняем новое расписание
    save_schedule(new_schedule)

def handle_updates():
    """Обрабатывает входящие сообщения от пользователя"""
    global CHAT_ID
    
    try:
        # Получаем обновления
        updates = bot.get_updates()
        
        for update in updates:
            if update.message:
                CHAT_ID = update.message.chat_id
                message_text = update.message.text.lower()
                
                if '/start' in message_text:
                    bot.send_message(
                        chat_id=CHAT_ID,
                        text=f"✅ Привет! Я настроен на группу <b>{GROUP_NAME}</b>\n\n"
                             f"Я буду отправлять уведомления при изменениях в расписании.\n\n"
                             f"Команды:\n"
                             f"/check - проверить расписание прямо сейчас\n"
                             f"/help - справка",
                        parse_mode='HTML'
                    )
                    logger.info(f"Chat ID установлен: {CHAT_ID}")
                    
                elif '/check' in message_text:
                    check_schedule()
                    
                elif '/help' in message_text:
                    bot.send_message(
                        chat_id=CHAT_ID,
                        text="<b>Доступные команды:</b>\n\n"
                             "/start - начало\n"
                             "/check - проверить расписание\n"
                             "/help - эта справка\n\n"
                             "Бот автоматически проверяет расписание каждый день "
                             "и отправляет уведомления при изменениях.",
                        parse_mode='HTML'
                    )
        
        # Сохраняем последний update_id
        if updates:
            with open('last_update_id.txt', 'w') as f:
                f.write(str(updates[-1].update_id))
    
    except Exception as e:
        logger.error(f"Ошибка при обработке обновлений: {e}")

def schedule_checks():
    """Планирует проверки расписания"""
    # Проверяем в 7:25 каждый день (после уведомления)
    schedule.every().day.at("07:25").do(check_schedule)
    
    # Дополнительные проверки в течение дня
    schedule.every().day.at("12:00").do(check_schedule)
    schedule.every().day.at("18:00").do(check_schedule)
    
    logger.info("Проверки расписания запланированы")

def main():
    """Главная функция"""
    logger.info("🤖 Telegram бот запущен!")
    logger.info(f"Мониторим расписание: {GROUP_NAME}")
    
    # Начальная проверка
    check_schedule()
    
    # Планируем проверки
    schedule_checks()
    
    # Основной цикл
    try:
        while True:
            # Обрабатываем входящие сообщения
            handle_updates()
            
            # Запускаем запланированные задачи
            schedule.run_pending()
            
            time.sleep(10)  # Проверяем каждые 10 секунд
    
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        send_notification(
            "🚨 Критическая ошибка",
            f"Бот упал с ошибкой:\n{str(e)}"
        )

if __name__ == "__main__":
    main()
