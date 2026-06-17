"""AI помощник"""
import requests
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import CallbackContext
from config import ADMIN_IDS
from database import db
from handlers_modules.common import is_admin
HTML = "HTML"

DEEPSEEK_API_KEY = "sk-05ba9b8e38b34c73bdbd40ebea2f3b29"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

async def ai_help(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        return
    context.user_data['asking_ai'] = True
    await update.message.reply_text(
        "🤖 <b>AI ПОМОЩНИК</b>\n\n"
        "Задайте вопрос — я отвечу!\n"
        "Для выхода напишите <b>выход</b>",
        parse_mode='HTML'
    )

async def ai_answer(update: Update, context: CallbackContext) -> None:
    if update.message.text.lower() in ['выход', 'exit', 'стоп']:
        context.user_data.pop('asking_ai', None)
        await update.message.reply_text("🤖 <b>AI завершён</b>", parse_mode='HTML')
        return
    
    await update.message.reply_text("🤖 <b>Думаю...</b>", parse_mode='HTML')
    
    def ask_deepseek(q):
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "deepseek-chat", "messages": [{"role": "system", "content": "Ты — поддержка VPN-сервиса SLK. Отвечай кратко, на русском."}, {"role": "user", "content": q}], "max_tokens": 500}
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
            if r.status_code == 200:
                return r.json()['choices'][0]['message']['content']
            return "❌ Ошибка AI"
        except:
            return "❌ Сервер AI недоступен"
    
    with ThreadPoolExecutor() as executor:
        future = executor.submit(ask_deepseek, update.message.text)
        answer = future.result()
    
    await update.message.reply_text(answer, parse_mode='HTML')
