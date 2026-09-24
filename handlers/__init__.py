from .start import router as start_router
from .balance import router as balance_router
from .image import router as image_router
from .edit import router as edit_router
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
from .helpers import user_pages, user_model

routers = [
    start_router,
    balance_router,
    image_router,
    edit_router,
    text_router,
    admin_router,
    payments_router,
    referral_router,
    promocode_router,
    file_router,
    voice_router,
    search_router,
    reminders_router,
    inline_router,
]
