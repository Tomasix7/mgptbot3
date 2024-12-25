# Файл: tts.py экспортируется в bot/handlers.py для основвного обработчика текста от пользователя
import os
import time
import logging
from datetime import datetime
from emoji import replace_emoji
import azure.cognitiveservices.speech as speechsdk
from telebot import TeleBot

# Конфигурация Azure Speech Service
SPEECH_KEY = os.getenv("SPEECH_KEY")
SPEECH_REGION = os.getenv("SPEECH_REGION", "eastus")

def remove_emoji(text):
    """Удаление эмодзи из текста"""
    return replace_emoji(text, '')

def cleanup_audio_file(file_path, max_attempts=5, delay=2):
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

def text_to_speech(bot: TeleBot, text: str, chat_id: int, voice_name="en-US-AvaMultilingualNeural"):
    """
    Преобразование текста в речь и отправка в Telegram
    Args:
        bot: объект бота
        text: текст для преобразования
        chat_id: ID чата для отправки
        voice_name: имя голоса Azure
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
        
        # Установка голоса
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
