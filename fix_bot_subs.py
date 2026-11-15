import os
import re

path = "bot.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"async def subscription_worker\(\):.*?(?=# === ВОРКЕР ЕЖЕДНЕВНОГО БЭКАПА|\n# ===|def smart_backup_worker|async def main)"

new_worker = '''async def subscription_worker():
    while True:
        try:
            now = datetime.now()
            in_3_days = (now + timedelta(days=3)).isoformat()
            
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, plan, premium_until FROM users
                    WHERE plan IN ('premium', 'premium_plus')
                    AND premium_until > ? AND premium_until <= ?
                """, (now.isoformat(), in_3_days))
                
                for row in cursor.fetchall():
                    user_id = row['user_id']
                    until = datetime.fromisoformat(row['premium_until'])
                    days_left = (until - now).days
                    plan_name = "Premium+" if row['plan'] == "premium_plus" else "Premium"
                    
                    text = (
                        f"⚠️ <b>Подписка {plan_name} заканчивается!</b>\\n\\n"
                        f"Осталось дней: <b>{days_left}</b>\\n"
                        f"Не забудь продлить, чтобы сохранить скидку и отсутствие водяных знаков!\\n\\n"
                        f"Продлить: /credits"
                    )
                    try:
                        await bot.send_message(user_id, text)
                    except Exception as e:
                        logger.warning(f"⚠️ Не отправил {user_id}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка воркера подписок: {e}")
        await asyncio.sleep(86400)

'''

new_content, count = re.subn(pattern, new_worker, content, flags=re.DOTALL)
if count > 0:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("✅ bot.py обновлен (уведомления за 3 дня)")
else:
    print("⚠️ Не удалось найти subscription_worker в bot.py")
