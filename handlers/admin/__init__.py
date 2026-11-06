from aiogram import Router
from .menu import router as menu_router
from .users import router as users_router
from .models import router as models_router
from .support import router as support_router
from .prices import router as prices_router

# Создаем главный роутер для всей админки
router = Router()

# Подключаем к нему дочерние роутеры
router.include_router(menu_router)
router.include_router(users_router)
router.include_router(models_router)
router.include_router(support_router)
router.include_router(prices_router)
