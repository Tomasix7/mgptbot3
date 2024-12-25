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
import time
import azure.cognitiveservices.speech as speechsdk
from emoji import replace_emoji
from config import TTS_ENABLED_USERS

# from devart import send_deviantart_image # функция отключена потому что devart повторяет одни и те же картинки

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Подключение к MongoDB
client = MongoClient(os.getenv("MONGO_URI"))
DBASE = os.getenv('DBASE')

db = client[DBASE]  # Для каждого бота и сервера своя база данных
users_collection = db["users_collection"]
characters_collection = db["characters"]  # Коллекция персонажей

# New Cod
# Конфигурация Azure Speech Service
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION", "eastus")

def remove_emoji(text):
    """Удаление эмодзи из текста"""
    return replace_emoji(text, '')

def cleanup_audio_file(file_path, max_attempts=5, delay=2):  # увеличили delay до 2 секунд
    """
    Функция для надёжного удаления файла с несколькими попытками
    """
    for attempt in range(max_attempts):
        try:
            if os.path.exists(file_path):
                os.close(os.open(file_path, os.O_RDONLY))  # Закрываем все хэндлы файла
                os.remove(file_path)
                logging.info(f"Файл {file_path} успешно удален")
                return True
        except Exception as e:
            if attempt < max_attempts - 1:
                logging.warning(f"Попытка {attempt + 1} удалить файл не удалась: {e}")
                time.sleep(delay)
            else:
                logging.error(f"Не удалось удалить файл после {max_attempts} попыток: {e}")
    return False

def text_to_speech(text, chat_id, voice_name="en-US-AvaMultilingualNeural"):
    """
    Преобразование текста в речь и отправка в Telegram
    Args:
        text: текст для преобразования
        chat_id: ID чата для отправки
        voice_name: имя голоса Azure (default: "en-US-AvaMultilingualNeural")
    """
    output_file = None
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"speech_{timestamp}.mp3"

        speech_config = speechsdk.SpeechConfig(
            subscription=SPEECH_KEY, 
            region=SPEECH_REGION
        )
        
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
        )
        
        # Use the provided voice name
        speech_config.speech_synthesis_voice_name = voice_name
        
        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
        
        speech_synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, 
            audio_config=audio_config
        )
        
        clean_text = remove_emoji(text)
        
        result = speech_synthesizer.speak_text_async(clean_text).get()
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            time.sleep(1)
            
            try:
                with open(output_file, 'rb') as audio_file:
                    bot.send_voice(chat_id, audio_file, timeout=30)
                logging.info(f"Аудио успешно отправлено в чат {chat_id}")
            except Exception as e:
                logging.error(f"Ошибка отправки аудио: {e}")
                raise
        else:
            logging.error(f"Ошибка синтеза речи: {result.reason}")
            
    except Exception as e:
        logging.error(f"Ошибка в функции text_to_speech: {e}")
        raise
    finally:
        if output_file:
            time.sleep(2)
            cleanup_audio_file(output_file)

def process_response_with_tts(response, chat_id, bot, users_gender, use_tts=False, object_id=None):
    """
    Обработка ответа и отправка текстового сообщения, аудио и изображения.
    """
    try:
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            response_content = response.choices[0].message.content
            logging.info(f'Получен ответ: {response_content}')
            
            cleaned_response = truncate_repeating_text(response_content)
            logging.info(f'Очищенный ответ: {cleaned_response}')

            # Закрыли получение картинок с Unsplash
            # image_url = get_random_image(users_gender)
            # if image_url:
            #     bot.send_photo(chat_id, image_url)
            # else:
            #     logging.warning("Не удалось получить URL изображения.")

            send_long_message(chat_id, bot, cleaned_response)
            dialogue_storage.add_message(chat_id, 'assistant', cleaned_response)

            if use_tts and object_id in TTS_ENABLED_USERS:
                time.sleep(1)
                voice_name = TTS_ENABLED_USERS[object_id]
                text_to_speech(cleaned_response, chat_id, voice_name)
        else:
            logging.error("Ответ от Groq пустой или не полностью получен, сообщение не отправлено.")
            bot.send_message(chat_id, "Извините, что-то пошло не так... 😊")
    except Exception as e:
        logging.error(f"Ошибка в process_response_with_tts: {e}")
        bot.send_message(chat_id, "Произошла ошибка при обработке сообщения... 😊")

# Stable Code        

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

def send_long_message(chat_id, bot, message):
    max_message_length = 4096
    # Разбиваем длинное сообщение на части, если оно превышает лимит
    for i in range(0, len(message), max_message_length):
        bot.send_message(chat_id, message[i:i+max_message_length])


def send_scheduled_message(object_id):
    try:
        # Проверка времени для разных пользователей
        if object_id == "670543779eed55e5c40145ea":  # ал
            utc_plus_5 = pytz.FixedOffset(5 * 60)
            current_time = datetime.now(utc_plus_5)
            
            if (
                current_time.hour < 7 
                or (8 <= current_time.hour < 11) 
                or (12 <= current_time.hour < 18) 
                or (19 <= current_time.hour < 21) 
                or (current_time.hour >= 23)
            ):
                logging.info(f"Скрипт завершен: ObjectID {object_id}, время {current_time.strftime('%H:%M')} UTC+5")
                return

        if object_id == "66fe7107ba9a8734f34b71cd":  # мн
            utc_plus_3 = pytz.FixedOffset(3 * 60)
            current_time = datetime.now(utc_plus_3)
            
            if (current_time.hour < 7 or 
                (8 <= current_time.hour < 9) or 
                (12 <= current_time.hour < 18) or 
                current_time.hour == 19 or 
                current_time.hour >= 23):
                
                logging.info(f"Скрипт завершен: ObjectID {object_id}, время {current_time.strftime('%H:%M')} UTC+3")
                return

        # Получение данных пользователя
        character_info, users_gender, timezone_offset, chat_id = get_user_and_character_data(object_id)

        if character_info is None:
            logging.error("Не удалось получить данные пользователя или персонажа.")
            return

        # Определяем, нужно ли использовать TTS для данного пользователя и какой голос.
        use_tts = object_id in TTS_ENABLED_USERS

        # Остальная логика формирования сообщения
        user_timezone = convert_numeric_timezone(timezone_offset).zone
        tz_manager = TimeZoneManager(user_timezone)
        current_hour = tz_manager.get_current_hour()
        base_prompt_file = tz_manager.get_prompt_for_time(current_hour)
        time_based_elements = tz_manager.get_elements_for_time(current_hour)
        
        now = datetime.now(tz_manager.default_timezone)
        today = now.strftime("%d.%m.%Y")
        current_time = now.strftime("%H:%M")

        today_elements = random.sample(time_based_elements, 2)
        final_prompt = f"{base_prompt_file}\nСегодня {today}, текущее время {current_time}. " \
                      f"Пожалуйста, включи в пожелание темы: {', '.join(today_elements)}. " \
                      f"Учитывай текущее время суток."

        # Получение истории диалога
        dialogue_history = dialogue_storage.get_messages(chat_id)[0:0]

        if len(dialogue_history) == 0:
            bot.send_message(chat_id, "🎉🥰")

        # Формирование сообщения для Groq
        messages_for_groq = [
            {"role": msg["role"], "content": msg["content"]} for msg in dialogue_history
        ]

        system_message = {
            "role": "system",
            "content": character_info
        }

        messages = [system_message] + messages_for_groq
        messages.append({"role": 'user', "content": final_prompt})

        # Отправка запроса в Groq
        response = client_groq.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{"role": 'user', "content": "\n".join([msg["content"] for msg in messages])}],
            temperature=0
        )

        # Обработка ответа с учетом TTS
        # process_response_with_tts(response, chat_id, bot, users_gender, use_tts)
        process_response_with_tts(response, chat_id, bot, users_gender, use_tts, object_id)

    except Exception as e:
        logging.error(f'Ошибка в функции send_scheduled_message: {e}')
        bot.send_message(chat_id, "Что-то пошло не так... 😊")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        logging.error("Неверное количество аргументов. Ожидался один аргумент - ObjectID.")
    else:
        object_id = sys.argv[1]
        send_scheduled_message(object_id)
