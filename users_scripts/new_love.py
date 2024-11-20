import os
import sys
# Добавляем путь к корневому каталогу проекта, чтобы импорт сверху проходил
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import logging
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import random
import pytz
from pytz import all_timezones_set
import re
from time_zone_manager import TimeZoneManager  # Импортируем свой модуль для управления часовыми поясами
from config import client_groq, bot  # Импортируем клиента и бота из файла конфигурации
from dialogue_storage import dialogue_storage  # Импортируем класс хранения диалогов
from unsplash_functions import get_random_image
# from devart import send_deviantart_image

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Подключение к MongoDB
client = MongoClient(os.getenv("MONGO_URI"))
DBASE = os.getenv('DBASE')

db = client[DBASE]  # Для каждого бота и сервера своя база данных
users_collection = db["users_collection"]
characters_collection = db["characters"]  # Коллекция персонажей

def convert_numeric_timezone(numeric_timezone):
    """Конвертирует числовой часовой пояс в pytz timezone."""
    try:
        offset_hours = int(numeric_timezone)

        # Поиск временной зоны на основе смещения
        matching_timezones = [tz for tz in all_timezones_set if 'GMT' not in tz and offset_hours == datetime.now(pytz.timezone(tz)).utcoffset().total_seconds() // 3600]
        
        if matching_timezones:
            return pytz.timezone(matching_timezones[0])  # Возвращаем первую найденную временную зону
        else:
            return pytz.UTC  # Если не найдено — по умолчанию UTC

    except ValueError:
        logging.error(f"Неверное значение часового пояса: {numeric_timezone}")
        return pytz.UTC

def get_user_and_character_data(object_id):
    """Получаем данные пользователя и персонажа по ObjectID."""
    try:
        # Поиск данных пользователя по ObjectID
        user_data = users_collection.find_one({"_id": ObjectId(object_id)})
        if not user_data:
            raise ValueError(f"Пользователь с ObjectID {object_id} не найден.")

        # Получаем данные о персонаже из коллекции characters
        character_name = user_data.get("character", "Default Character")
        character_data = characters_collection.find_one({"character": character_name})
        if not character_data:
            raise ValueError(f"Персонаж с именем {character_name} не найден в коллекции characters.")

        character_description = character_data.get("description", "Описание не найдено.")
        users_gender = user_data.get("users_gender", "unknown")
        timezone_offset = user_data.get("timezone", 0)

        return character_description, users_gender, timezone_offset, user_data.get("chat_id")
    except Exception as e:
        logging.error(f"Ошибка при получении данных пользователя или персонажа: {e}")
        return None, None, None, None
    

def get_random_elements(elements, n):
    return random.sample(elements, min(n, len(elements)))

def split_message(message, max_length):
    """Разбивает длинное сообщение на части, не превышающие max_length."""
    return [message[i:i + max_length] for i in range(0, len(message), max_length)]

def truncate_repeating_text(text, max_repeats=3):
    """Обрезает повторяющиеся слова и символы."""
    
    # Убираем слишком длинные повторы символов (например, 'срсрсрсрс...')
    def limit_repeated_chars(match):
        char_sequence = match.group(0)
        return char_sequence[:max_repeats]
    
    # Шаблон для поиска повторяющихся символов
    text = re.sub(r'(.)\1{3,}', limit_repeated_chars, text)

    words = text.split()
    result = []
    prev_word = None
    repeat_count = 0
    
    # Обработка повторяющихся слов
    for word in words:
        if word == prev_word:
            repeat_count += 1
        else:
            repeat_count = 0
        
        if repeat_count < max_repeats:
            result.append(word)
        
        prev_word = word
    
    return ' '.join(result)

def process_response(response, chat_id, bot, users_gender):
    """Обрабатывает ответ от Groq, обрезая повторяющиеся символы."""
    if response.choices and response.choices[0].message and response.choices[0].message.content:
        response_content = response.choices[0].message.content
        logging.info(f'Получен ответ: {response_content}')
        logging.info(f'Длина ответа от Groq: {len(response_content)}')

        # Убираем повторяющиеся символы или слова
        cleaned_response = truncate_repeating_text(response_content)
        logging.info(f'Очищенный ответ: {cleaned_response}')

        image_url = get_random_image(users_gender)
        if image_url:
            bot.send_photo(chat_id, image_url)
        else:
            logging.error("url изображения так не получается...")

        send_long_message(chat_id, bot, cleaned_response)
        dialogue_storage.add_message(chat_id, 'assistant', cleaned_response)
    else:
        logging.error("Ответ от Groq пустой или не полностью получен, сообщение не отправлено.")
        bot.send_message(chat_id, "Опять я это самое... 🤪")

def send_long_message(chat_id, bot, message):
    max_message_length = 4096
    # Разбиваем длинное сообщение на части, если оно превышает лимит
    for i in range(0, len(message), max_message_length):
        bot.send_message(chat_id, message[i:i+max_message_length])


def send_scheduled_message(object_id):
    logging.info(f"=== Начало выполнения send_scheduled_message для object_id: {object_id} ===")
    try:
        logging.info("Проверка ID для временных ограничений")
        # Отключение отправки сообщения в тихие часы.
        if object_id == "670543779eed55e5c40145ea": # ал
            # Создаем часовой пояс UTC+5
            utc_plus_5 = pytz.FixedOffset(5 * 60)  # 5 hours * 60 minutes
            
            # Получаем текущее время в UTC+5
            current_time = datetime.now(utc_plus_5)
            
            # Проверяем, попадает ли время в заданный диапазон UTC+5
            if current_time.hour < 7 or 13 <= current_time.hour < 18:
            # if current_time.hour < 7 or 10 < current_time.hour < 12:
                logging.info(f"Скрипт завершен: ObjectID {object_id}, время {current_time.strftime('%H:%M')} UTC+5")
                return  # Завершаем выполнение функции
        
        if object_id == "66fe7107ba9a8734f34b71cd": # мн
            logging.info("Start handle schedule instructions")

            # # Этот вариант обработки серверного времени не работает на Render
            # # Создаем часовой пояс UTC+3
            # utc_plus_3 = pytz.FixedOffset(3 * 60)  # 3 hours * 60 minutes
            # # Получаем текущее время в UTC+3
            # current_time = datetime.now(utc_plus_3)

            # Создаем часовой пояс UTC+3
            timezone = pytz.timezone('Europe/Moscow')  # UTC+3
            
            # Получаем текущее время в UTC и конвертируем в UTC+3
            utc_now = datetime.now(pytz.UTC)
            current_time = utc_now.astimezone(timezone)
        
            logging.info(f'UTC время: {utc_now}, Локальное время (UTC+3): {current_time}')
            logging.info(f'current_time.hour = {current_time.hour}')
            
            # Добавим более подробное логирование условий
            logging.info(f"""Проверка условий:
            current_time.hour < 7: {current_time.hour < 7}
            8 <= current_time.hour < 11: {8 <= current_time.hour < 11}
            12 <= current_time.hour < 18: {12 <= current_time.hour < 18}
            current_time.hour == 19: {current_time.hour == 19}
            current_time.hour >= 23: {current_time.hour >= 23}
            """)

            # Проверяем, попадает ли время в заданный  диапазон UTC+3
            # if current_time.hour < 7 or 13 <= current_time.hour < 18:

            if (current_time.hour < 7 or 
                (8 <= current_time.hour < 11) or 
                (12 <= current_time.hour < 18) or 
                current_time.hour == 19 or 
                current_time.hour >= 23):

                logging.info(f"Скрипт завершен: ObjectID {object_id}, время {current_time.strftime('%H:%M')} UTC+3")
                return  # Завершаем выполнение функции
            else:
                logging.info('Schedule instructions were ignored')
        # Получаем данные пользователя и персонажа из базы по ObjectID
        character_info, users_gender, timezone_offset, chat_id = get_user_and_character_data(object_id)

        if character_info is None:
            logging.error("Не удалось получить данные пользователя или персонажа.")
            return

        # Преобразуем числовой часовой пояс в pytz и передаем строку (через .zone)
        user_timezone = convert_numeric_timezone(timezone_offset).zone
        logging.info(f'Часовой пояс пользователя: {user_timezone}')

        # Передаем строку в TimeZoneManager
        tz_manager = TimeZoneManager(user_timezone)

        # Получаем текущий час
        current_hour = tz_manager.get_current_hour()
        logging.info(f'Текущий час: {current_hour}')

        base_prompt_file = tz_manager.get_prompt_for_time(current_hour)
        logging.info(f'Промпт из файла: {base_prompt_file}')

        time_based_elements = tz_manager.get_elements_for_time(current_hour)
        logging.info(f'Элементы по времени: {time_based_elements}')

        # Новая версия передачи текущего времени в промт
        now = datetime.now(tz_manager.default_timezone)
        today = now.strftime("%d.%m.%Y")
        current_time = now.strftime("%H:%M")

        # # Добавляем случайные элементы в сообщение
        today_elements = random.sample(time_based_elements, 2)
        # today = datetime.now(tz_manager.default_timezone).strftime("%d.%m.%Y")
        # final_prompt = f"{base_prompt_file}\nСегодня {today}. Пожалуйста, включи в пожелание темы: {', '.join(today_elements)}."

        final_prompt = f"{base_prompt_file}\nСегодня {today}, текущее время {current_time}. " \
               f"Пожалуйста, включи в пожелание темы: {', '.join(today_elements)}. " \
               f"Учитывай текущее время суток."

        logging.info(f'Длина финального промпта: {len(final_prompt)}')

        # Получаем историю диалога из хранения
        dialogue_history = dialogue_storage.get_messages(chat_id)[0:0]
        logging.info(f'История диалога для chat_id {chat_id}: {dialogue_history}')

        if len(dialogue_history) == 0:
            bot.send_message(chat_id, "🎉🥰")

        messages_for_groq = [
            {"role": msg["role"], "content": msg["content"]} for msg in dialogue_history
        ]

        system_message = {
            "role": "system",
            "content": character_info
        }

        messages = [system_message] + messages_for_groq
        messages.append({"role": 'user', "content": final_prompt})

        combined_messages = [msg["content"] for msg in messages]
        full_message = "\n".join(combined_messages)

        logging.info(f'Окончательная длина запроса к Groq: {len(full_message)}')
        logging.info(f'Окончательная длина запроса к Groq: {full_message}')

        # Отправляем сообщение в Groq
        response = client_groq.chat.completions.create(
            model='llama-3.1-70b-versatile',
            messages=[{"role": 'user', "content": full_message}],
            temperature=0
        )

        # Обрабатываем ответ и отправляем сообщение пользователю
        process_response(response, chat_id, bot, users_gender)
    except AttributeError as e:
        logging.error(f'Ошибка в функции send_scheduled_message: {e}')
        bot.send_message(chat_id, "Что-то пошло не так с часовым поясом... 😊")
    except Exception as e:
        logging.error(f'Ошибка в функции send_scheduled_message: {e}')
        bot.send_message(chat_id, "Что-то пошло не так... 😊")

if __name__ == '__main__':
    # Вызов DeviantArt функции перед send_scheduled_message
    # send_deviantart_image()

    if len(sys.argv) != 2:
        logging.error("Неверное количество аргументов. Ожидался один аргумент - ObjectID.")
    else:
        object_id = sys.argv[1]
        send_scheduled_message(object_id)
