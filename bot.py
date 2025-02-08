import os
import asyncio
import random
from datetime import datetime, timedelta
from loguru import logger
from telethon import TelegramClient, events, Button
from telethon.errors import (
    FloodWaitError, SlowModeWaitError,
    ChatWriteForbiddenError, PeerIdInvalidError,
    ChannelPrivateError, UserBannedInChannelError,
    UnauthorizedError, RPCError
)
from telethon.tl.functions.messages import ForwardMessagesRequest

# Логирование
logger.add("debug.log", format="{time} {level} {message}", level="INFO")

class SpamBotClient:
    def __init__(self, session_file):
        self.clients = []
        self.session_file = session_file
        self.delay_range = (0.5, 2)  # Задержка между отправками (секунды)
        self.cycle_interval = (8, 15)  # Задержка между циклами (минуты)
        self.report_chat = "https://t.me/infoinfoinfoinfoo"  # Чат для отчетов
        self.last_message_time = {}  # Время последней отправки сообщения
        self.sent_messages_count = {}  # Количество отправленных сообщений

        self._init_environment()
        self.session_configs = self._load_sessions()
        self._init_clients()

    def _init_environment(self):
        os.makedirs('sessions', exist_ok=True)
    
    def _load_sessions(self):
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                return [self._parse_session_line(line) for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Ошибка загрузки сессий: {str(e)}")
            return []

    def _parse_session_line(self, line):
        parts = line.strip().split(',')
        if len(parts) != 4:
            logger.error(f"Некорректный формат строки: {line.strip()}")
            return None
        return {
            'session_name': parts[0].strip(),
            'api_id': int(parts[1].strip()),
            'api_hash': parts[2].strip(),
            'phone': parts[3].strip()
        }

    def _init_clients(self):
        for config in self.session_configs:
            client = TelegramClient(
                f'sessions/{config["session_name"]}',
                config['api_id'],
                config['api_hash']
            )
            client.phone = config['phone']
            self.clients.append(client)

    async def forward_messages(self, client):
        sent_count = 0
        try:
            dialogs = await client.get_dialogs()
            target_chats = [d for d in dialogs if d.is_group or d.is_channel]
            messages = await client.get_messages("me", limit=5)  # Берем 5 последних сообщений из "Избранного"
            
            if not messages:
                logger.warning(f"❌ Нет сообщений в 'Избранном' для {client.phone}")
                return sent_count

            random.shuffle(target_chats)
            for chat in target_chats:
                msg = random.choice(messages)  # Выбираем случайное сообщение
                try:
                    await client(ForwardMessagesRequest(
                        from_peer="me",
                        id=[msg.id],
                        to_peer=chat
                    ))
                    self.sent_messages_count[client.phone] = self.sent_messages_count.get(client.phone, 0) + 1
                    self.last_message_time[client.phone] = datetime.now()
                    sent_count += 1
                    logger.success(f"📨 Сообщение переслано в {chat.name} ({client.phone})")
                    await asyncio.sleep(random.uniform(*self.delay_range) / 2)
                except (ChatWriteForbiddenError, PeerIdInvalidError, ChannelPrivateError, UserBannedInChannelError) as e:
                    logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
                except RPCError as e:
                    logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
                except Exception as e:
                    logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
        except Exception as e:
            logger.error(f"⚠️ Ошибка пересылки сообщений {client.phone}: {str(e)}")
        return sent_count

    async def handle_spam_bot(self, client):
        if datetime.now() - self.last_message_time.get(client.phone, datetime.min) < timedelta(minutes=15):
            return
        
        logger.warning(f"🆘 {client.phone} не отправлял сообщения 15 минут. Обращаемся к @SpamBot")
        try:
            spam_bot = await client.get_entity("SpamBot")
            async with client.conversation(spam_bot) as conv:
                await conv.send_message("/start")
                response = await conv.get_response()
                
                if "ограничение" in response.text and response.buttons:
                    button_texts = ["Ок", "Продолжить", "Подтвердить"]
                    for text in button_texts:
                        for row in response.buttons:
                            for button in row:
                                if text in button.text:
                                    await conv.click(button)
                                    logger.info(f"🔘 Нажата кнопка: {button.text} ({client.phone})")
                                    await asyncio.sleep(random.randint(2, 5))
                                    break
        except FloodWaitError as e:
            logger.error(f"❌ FloodWait @SpamBot: ждем {e.seconds} сек")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"❌ Ошибка @SpamBot для {client.phone}: {str(e)}")

    async def send_report(self, client, sent_count, total_chats, delay_minutes):
        report_message = (
            f"📊 Отчет о рассылке:\n"
            f"Аккаунт: {client.phone}\n"
            f"Отправлено сообщений: {sent_count}\n"
            f"Всего чатов: {total_chats}\n"
            f"Следующая рассылка через: {delay_minutes} минут"
        )
        try:
            await client.send_message(self.report_chat, report_message)
            logger.success(f"📨 Отчет отправлен в {self.report_chat} ({client.phone})")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчета для {client.phone}: {str(e)}")

    async def start(self):
        # Инициализация клиентов
        for client in self.clients:
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    logger.error(f"❌ {client.phone} не авторизован. Требуется вход в аккаунт!")
                    continue
                logger.success(f"✅ Успешно авторизован: {client.phone}")
            except Exception as e:
                logger.error(f"Ошибка инициализации {client.phone}: {str(e)}")
        
        while True:
            # Создаем список задач для параллельного выполнения
            tasks = []
            for client in self.clients:
                task = asyncio.create_task(self._process_client(client))
                tasks.append(task)
            
            # Ждем выполнения всех задач
            await asyncio.gather(*tasks)
            
            delay_minutes = random.randint(*self.cycle_interval)
            logger.info(f"⏳ Ожидание {delay_minutes} минут...")
            await asyncio.sleep(delay_minutes * 60)

    async def _process_client(self, client):
        """Обработка одного клиента"""
        sent_count = await self.forward_messages(client)
        dialogs = await client.get_dialogs()
        total_chats = len(dialogs)
        await self.handle_spam_bot(client)
        delay_minutes = random.randint(*self.cycle_interval)
        await self.send_report(client, sent_count, total_chats, delay_minutes)

async def main():
    session_file = "sessions.txt"
    bot_client = SpamBotClient(session_file)
    await bot_client.start()

if __name__ == "__main__":
    asyncio.run(main())