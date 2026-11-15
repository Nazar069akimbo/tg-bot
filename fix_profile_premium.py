import os
import re

path = "handlers/profile.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = r"premium_line = \"\".*?(?=text = \()"

new_block = '''premium_line = ""
    if plan in ("premium", "premium_plus"):
        emoji = "💎" if plan == "premium" else "👑"
        premium_line = f"\\n{emoji} <b>Подписка {plan_name}</b>"
        if premium_until:
            try:
                until_dt = datetime.fromisoformat(premium_until)
                days_left = (until_dt - datetime.now()).days
                premium_line += f" (осталось {days_left} дн.)"
            except: pass
        premium_line += "\\n✨ <i>Приоритетная поддержка, без водяных знаков и скидка 20%!</i>"

    '''
content = re.sub(pattern, new_block, content, flags=re.DOTALL)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ handlers/profile.py обновлен (красивая плашка Premium)")
