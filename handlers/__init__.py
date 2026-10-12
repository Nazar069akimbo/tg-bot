from .start import router as start_router
from .balance import router as balance_router
from .image import router as image_router
from .text import router as text_router
from .admin import router as admin_router
from .payments import router as payments_router
from .referral import router as referral_router
from .promocode import router as promocode_router
from .file import router as file_router
from .voice import router as voice_router
from .search import router as search_router
from .reminders import router as reminders_router
from .inline import router as inline_router
from .profile import router as profile_router
from .help import router as help_router
from .memory import router as memory_router
from .support import router as support_router
from .bonus import router as bonus_router
from .helpers import user_pages, user_model

# ВАЖНО: специфичные роутеры идут ПЕРВЫМИ,
# а text_router (который ловит всё) — В САМОМ КОНЦЕ!

routers = [
    # 1. Команды и специальные хендлеры
    start_router,
    balance_router,
    profile_router,
    help_router,
    payments_router,
    referral_router,
    promocode_router,
    reminders_router,
    bonus_router,
    admin_router,
    search_router,
    memory_router,
    support_router,

    # 2. Медиа
    image_router,
    file_router,
    voice_router,
    inline_router,

    # 3. Текст — САМЫЙ ПОСЛЕДНИЙ!
    text_router,
]
