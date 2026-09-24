from aiogram import Router, types, F
from aiogram.filters import Command
from database.db import *
from datetime import datetime, timedelta
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("remind"))
async def set_reminder(message: types.Message):
    user_id = message.from_user.id
    text = message.text.replace("/remind", "").strip()
    
    if not text:
        await message.answer("❌ Формат: /remind 10:00 Текст")
        return
    
    try:
        parts = text.split(" ", 1)
        if len(parts) < 2:
            await message.answer("❌ Формат: /remind 10:00 Текст")
            return
        
        time_str = parts[0]
        reminder_text = parts[1]
        
        today = datetime.now().date()
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        full_time = datetime.combine(today, time_obj)
        
        if full_time < datetime.now():
            full_time = full_time + timedelta(days=1)
        
        add_reminder(user_id, reminder_text, full_time.isoformat())
        
        await message.answer(f"⏰ **Напоминание установлено!**\n\n📝 {reminder_text}\n🕐 {full_time.strftime('%d.%m.%Y %H:%M')}")
        
    except ValueError:
        await message.answer("❌ Неверный формат. Используй: /remind 10:00 Текст")

@router.message(Command("reminders"))
async def list_reminders(message: types.Message):
    user_id = message.from_user.id
    reminders = get_user_reminders(user_id)
    
    if not reminders:
        await message.answer("📭 Нет активных напоминаний")
        return
    
    text = "⏰ **Напоминания:**\n\n"
    for r in reminders:
        time_str = datetime.fromisoformat(r['time']).strftime('%d.%m %H:%M')
        text += f"• {time_str} — {r['text']}\n"
    
    await message.answer(text)
