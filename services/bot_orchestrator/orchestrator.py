import asyncio
import aiohttp
import aio_pika
import asyncpg
import aioredis
import uvloop
import docker
import json
import time
import hashlib
import os
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import logging
import traceback

# ==================== تنظیمات ====================
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'postgres'),
    'port': 5432,
    'user': 'admin',
    'password': os.getenv('DB_PASSWORD', ''),
    'database': 'bot_empire',
    'min_size': 100,
    'max_size': 1000,
    'command_timeout': 60,
    'max_queries': 50000,
    'max_inactive_connection_lifetime': 300
}

REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis'),
    'port': 6379,
    'password': os.getenv('REDIS_PASS', ''),
    'max_connections': 10000,
    'decode_responses': True
}

RABBITMQ_CONFIG = {
    'host': os.getenv('RABBITMQ_HOST', 'rabbitmq'),
    'login': 'admin',
    'password': os.getenv('RABBITMQ_PASS', ''),
    'port': 5672
}

# ==================== لاگینگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== دیتا کلاس‌ها ====================
@dataclass
class BotInstance:
    id: int
    user_id: int
    token: str
    name: str
    username: str
    container_id: str
    status: str
    cpu_usage: float
    memory_usage: float
    created_at: datetime
    last_active: datetime

@dataclass
class ServerNode:
    id: str
    host: str
    cpu_total: int
    cpu_used: int
    memory_total: int
    memory_used: int
    disk_total: int
    disk_used: int
    running_bots: int
    status: str

# ==================== اورکستریتور اصلی ====================
class BotOrchestrator:
    def __init__(self):
        self.docker_client = docker.from_env()
        self.db_pool = None
        self.redis = None
        self.rabbitmq = None
        self.nodes: Dict[str, ServerNode] = {}
        self.bots: Dict[int, BotInstance] = {}
        self.executor = ThreadPoolExecutor(max_workers=1000)
        self.running = True
        
    async def initialize(self):
        """راه‌اندازی اتصالات"""
        # PostgreSQL
        self.db_pool = await asyncpg.create_pool(**DB_CONFIG)
        
        # Redis
        self.redis = await aioredis.from_url(
            f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}",
            password=REDIS_CONFIG['password'],
            max_connections=REDIS_CONFIG['max_connections'],
            decode_responses=REDIS_CONFIG['decode_responses']
        )
        
        # RabbitMQ
        self.rabbitmq = await aio_pika.connect_robust(
            host=RABBITMQ_CONFIG['host'],
            login=RABBITMQ_CONFIG['login'],
            password=RABBITMQ_CONFIG['password'],
            port=RABBITMQ_CONFIG['port']
        )
        
        # شروع تسک‌ها
        asyncio.create_task(self.monitor_nodes())
        asyncio.create_task(self.monitor_bots())
        asyncio.create_task(self.process_queue())
        asyncio.create_task(self.load_balancer())
        
        logger.info("✅ Orchestrator initialized successfully")
    
    async def create_bot(self, user_id: int, files: Dict, token: str) -> Dict:
        """ایجاد ربات جدید با Docker"""
        try:
            start_time = time.time()
            
            # پیدا کردن بهترین نود
            node = await self.find_best_node()
            if not node:
                return {'success': False, 'error': 'No available nodes'}
            
            # آیدی یکتا برای ربات
            bot_id = hashlib.md5(f"{user_id}_{token}_{time.time()}".encode()).hexdigest()[:16]
            
            # ایجاد Dockerfile
            dockerfile = f'''
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
'''
            
            # ساخت image
            image_tag = f"bot_{bot_id}:latest"
            image, logs = self.docker_client.images.build(
                path=f"/tmp/bot_{bot_id}",
                dockerfile="Dockerfile",
                tag=image_tag,
                rm=True
            )
            
            # اجرا کانتینر
            container = self.docker_client.containers.run(
                image=image_tag,
                name=f"bot_{bot_id}",
                environment={
                    'TOKEN': token,
                    'BOT_ID': bot_id,
                    'USER_ID': user_id
                },
                mem_limit='512m',
                cpu_period=100000,
                cpu_quota=50000,  # 0.5 CPU
                network='bot_network',
                detach=True,
                restart_policy={"Name": "always"},
                labels={
                    'bot_id': bot_id,
                    'user_id': str(user_id),
                    'type': 'telegram_bot'
                }
            )
            
            # ذخیره در دیتابیس
            async with self.db_pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO bots (id, user_id, token, name, username, container_id, node, status, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ''', bot_id, user_id, token, f"Bot {bot_id[:8]}", f"bot_{bot_id[:8]}", 
                    container.id, node.id, 'running', datetime.now())
            
            # کش در Redis
            await self.redis.setex(
                f"bot:{bot_id}",
                3600,
                json.dumps({
                    'container_id': container.id,
                    'node': node.id,
                    'status': 'running'
                })
            )
            
            # ارسال به RabbitMQ برای پردازش
            channel = await self.rabbitmq.channel()
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps({
                        'type': 'bot_created',
                        'bot_id': bot_id,
                        'user_id': user_id
                    }).encode()
                ),
                routing_key='bot_events'
            )
            
            response_time = time.time() - start_time
            logger.info(f"✅ Bot {bot_id} created in {response_time:.3f}s")
            
            return {
                'success': True,
                'bot_id': bot_id,
                'container_id': container.id,
                'node': node.id,
                'response_time': response_time
            }
            
        except Exception as e:
            logger.error(f"Error creating bot: {e}\n{traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def find_best_node(self) -> Optional[ServerNode]:
        """پیدا کردن بهترین نود برای اجرای ربات"""
        available = [n for n in self.nodes.values() if n.status == 'healthy']
        
        if not available:
            return None
        
        # محاسبه امتیاز
        def score(node: ServerNode) -> float:
            cpu_score = 1 - (node.cpu_used / node.cpu_total)
            mem_score = 1 - (node.memory_used / node.memory_total)
            bot_score = 1 - (node.running_bots / 1000)  # max 1000 bots per node
            return cpu_score * 0.4 + mem_score * 0.4 + bot_score * 0.2
        
        return max(available, key=score)
    
    async def monitor_nodes(self):
        """مانیتورینگ نودها"""
        while self.running:
            try:
                # دریافت اطلاعات از Docker Swarm
                nodes = self.docker_client.nodes.list()
                
                for node in nodes:
                    spec = node.attrs['Spec']
                    status = node.attrs['Status']
                    
                    # محاسبه منابع
                    resources = node.attrs['Description']['Resources']
                    cpu_total = resources['NanoCPUs'] / 1e9
                    memory_total = resources['MemoryBytes'] / (1024**3)
                    
                    # دریافت ربات‌های در حال اجرا روی این نود
                    containers = self.docker_client.containers.list(
                        filters={
                            'label': 'type=telegram_bot',
                            'node': node.id
                        }
                    )
                    
                    self.nodes[node.id] = ServerNode(
                        id=node.id,
                        host=status['Addr'],
                        cpu_total=cpu_total,
                        cpu_used=len(containers) * 0.5,  # هر ربات 0.5 CPU
                        memory_total=memory_total,
                        memory_used=len(containers) * 0.5,  # هر ربات 512MB
                        disk_total=1000,
                        disk_used=len(containers) * 0.1,
                        running_bots=len(containers),
                        status='healthy' if status['State'] == 'ready' else 'unhealthy'
                    )
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Monitor nodes error: {e}")
                await asyncio.sleep(10)
    
    async def monitor_bots(self):
        """مانیتورینگ ربات‌ها"""
        while self.running:
            try:
                containers = self.docker_client.containers.list(
                    filters={'label': 'type=telegram_bot'}
                )
                
                for container in containers:
                    stats = container.stats(stream=False)
                    
                    cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                               stats['precpu_stats']['cpu_usage']['total_usage']
                    system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                                  stats['precpu_stats']['system_cpu_usage']
                    
                    cpu_percent = 0.0
                    if system_delta > 0 and cpu_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * 100
                    
                    memory_usage = stats['memory_stats']['usage'] / (1024**2)
                    
                    bot_id = container.labels.get('bot_id')
                    await self.redis.setex(
                        f"bot_stats:{bot_id}",
                        60,
                        json.dumps({
                            'cpu': cpu_percent,
                            'memory': memory_usage,
                            'status': container.status
                        })
                    )
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Monitor bots error: {e}")
                await asyncio.sleep(10)
    
    async def process_queue(self):
        """پردازش صف درخواست‌ها"""
        channel = await self.rabbitmq.channel()
        queue = await channel.declare_queue('bot_requests', durable=True)
        
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body)
                        
                        if data['type'] == 'create_bot':
                            await self.create_bot(
                                data['user_id'],
                                data['files'],
                                data['token']
                            )
                        elif data['type'] == 'stop_bot':
                            await self.stop_bot(data['bot_id'])
                        elif data['type'] == 'restart_bot':
                            await self.restart_bot(data['bot_id'])
                            
                    except Exception as e:
                        logger.error(f"Queue process error: {e}")
    
    async def load_balancer(self):
        """تعادل بار بین نودها"""
        while self.running:
            try:
                # دریافت آمار همه نودها
                stats = []
                for node_id, node in self.nodes.items():
                    if node.status == 'healthy':
                        stats.append({
                            'node_id': node_id,
                            'load': (node.cpu_used / node.cpu_total) * 100,
                            'bots': node.running_bots
                        })
                
                # اگر نودی بیش از حد شلوغ بود، ربات‌هاش رو جابجا کن
                for stat in stats:
                    if stat['load'] > 80:  # بالای 80%
                        await self.rebalance_node(stat['node_id'])
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Load balancer error: {e}")
                await as.sync(30)
    
    async def rebalance_node(self, node_id: str):
        """جابجایی ربات‌های یک نود شلوغ"""
        try:
            # پیدا کردن ربات‌های این نود
            containers = self.docker_client.containers.list(
                filters={
                    'label': 'type=telegram_bot',
                    'node': node_id
                }
            )
            
            for container in containers[:10]:  # حداکثر ۱۰ تا
                # پیدا کردن نود جدید
                new_node = await self.find_best_node()
                if new_node and new_node.id != node_id:
                    # سرویس رو به نود جدید منتقل کن
                    service = self.docker_client.services.create(
                        f"bot_{container.labels['bot_id']}",
                        placement=[new_node.id]
                    )
                    
                    # حذف کانتینر قدیمی
                    container.stop()
                    container.remove()
                    
                    logger.info(f"✅ Bot {container.labels['bot_id']} moved to node {new_node.id}")
                    
        except Exception as e:
            logger.error(f"Rebalance error: {e}")
    
    async def stop_bot(self, bot_id: str) -> bool:
        """توقف ربات"""
        try:
            # پیدا کردن کانتینر
            containers = self.docker_client.containers.list(
                filters={'label': f'bot_id={bot_id}'}
            )
            
            if containers:
                containers[0].stop()
                containers[0].remove()
                
                # آپدیت دیتابیس
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE bots SET status = $1 WHERE id = $2',
                        'stopped', bot_id
                    )
                
                # حذف از کش
                await self.redis.delete(f"bot:{bot_id}")
                
                logger.info(f"✅ Bot {bot_id} stopped")
                return True
                
        except Exception as e:
            logger.error(f"Stop bot error: {e}")
        
        return False
    
    async def restart_bot(self, bot_id: str) -> bool:
        """راه‌اندازی مجدد ربات"""
        try:
            await self.stop_bot(bot_id)
            await asyncio.sleep(2)
            
            # دریافت اطلاعات از دیتابیس
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT * FROM bots WHERE id = $1',
                    bot_id
                )
            
            if row:
                return await self.create_bot(
                    row['user_id'],
                    {},  # فایل‌ها باید از MinIO خونده بشن
                    row['token']
                )
                
        except Exception as e:
            logger.error(f"Restart bot error: {e}")
        
        return False
    
    async def cleanup(self):
        """پاک‌سازی منابع"""
        self.running = False
        
        if self.db_pool:
            await self.db_pool.close()
        
        if self.redis:
            await self.redis.close()
        
        if self.rabbitmq:
            await self.rabbitmq.close()
        
        self.executor.shutdown()

# ==================== اجرا ====================
async def main():
    orchestrator = BotOrchestrator()
    
    try:
        await orchestrator.initialize()
        
        # منتظر بمون تا سرویس متوقف بشه
        while orchestrator.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await orchestrator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
