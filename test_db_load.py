import asyncio
import time
import random
from database.db import *
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_user_operation(user_id, operation_id):
    """Имитация действия пользователя"""
    start = time.time()
    
    try:
        user = get_user(user_id)
        if not user:
            create_user(user_id, f"user_{user_id}")
            logger.info(f"✅ [{operation_id}] Пользователь {user_id} создан")
        
        tokens = get_tokens(user_id)
        
        if random.random() > 0.5:
            add_tokens(user_id, random.randint(1, 10))
            logger.info(f"✅ [{operation_id}] + токены пользователю {user_id}")
        
        if random.random() > 0.9:
            stats = get_stats()
            logger.info(f"✅ [{operation_id}] Статистика: {stats}")
        
        elapsed = time.time() - start
        logger.info(f"✅ [{operation_id}] Готово за {elapsed:.2f}с")
        return True
        
    except Exception as e:
        logger.error(f"❌ [{operation_id}] Ошибка: {e}")
        return False

async def test_load(users=10, operations=5):
    logger.info(f"🚀 ЗАПУСК ТЕСТА НАГРУЗКИ")
    logger.info(f"👥 Пользователей: {users}")
    logger.info(f"🔄 Операций на пользователя: {operations}")
    logger.info(f"📊 Всего операций: {users * operations}")
    
    start_time = time.time()
    
    tasks = []
    for i in range(users):
        user_id = 1000000 + i
        for j in range(operations):
            tasks.append(test_user_operation(user_id, f"{i+1}_{j+1}"))
    
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    success = sum(results)
    failed = len(results) - success
    
    logger.info(f"""
📊 **РЕЗУЛЬТАТЫ ТЕСТА**
━━━━━━━━━━━━━━━━━━━━━━━
✅ Успешно: {success}
❌ Ошибок: {failed}
⏱️ Время: {elapsed:.2f}с
📈 Операций/сек: {len(results) / elapsed:.1f}
    """)
    
    logger.info(get_queue_info())

async def test_single_operation():
    logger.info("🧪 ТЕСТ ОДНОЙ ОПЕРАЦИИ")
    
    user_id = 999999
    start = time.time()
    
    user = get_user(user_id)
    if not user:
        create_user(user_id, "test_user")
        logger.info("✅ Пользователь создан")
    
    tokens = get_tokens(user_id)
    logger.info(f"💰 Токенов: {tokens}")
    
    add_tokens(user_id, 100)
    tokens = get_tokens(user_id)
    logger.info(f"💰 Токенов после добавления: {tokens}")
    
    elapsed = time.time() - start
    logger.info(f"⏱️ Время: {elapsed:.2f}с")
    
    logger.info(get_queue_info())

def show_queue_status():
    print(get_queue_info())

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
📋 Использование:
  python test_db_load.py single    - тест одной операции
  python test_db_load.py load 10 5 - тест нагрузки (10 пользователей, 5 операций)
  python test_db_load.py status   - статус очереди
        """)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "single":
        asyncio.run(test_single_operation())
    elif command == "load":
        users = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        ops = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        asyncio.run(test_load(users, ops))
    elif command == "status":
        show_queue_status()
    else:
        print("❌ Неизвестная команда")
