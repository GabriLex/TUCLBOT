import asyncio
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.errors import (
    RPCError, FloodWaitError,
    SessionPasswordNeededError,
    PhoneNumberUnoccupiedError
)

# Configurazione da variabili d'ambiente
import os
BOT_TOKEN = os.environ['BOT_TOKEN']
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']

app = Flask(__name__)

class TUCLBot:
    def __init__(self):
        # Stato del bot
        self.client = None
        self.user_sessions = {}  # Sessioni utente
        self.login_attempts = {}  # Tentativi di login
        self.limited_mode = False  # Modalità limitata
        self.allowed_chats = set()  # Chat autorizzate

        # Configurazione logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    async def init_user_session(self, user_id, api_id=None, api_hash=None, phone=None, code=None, password=None):
        """Gestione completa del login utente"""
        try:
            # Disconnessione sessioni esistenti
            if user_id in self.user_sessions:
                await self.user_sessions[user_id].disconnect()

            client = TelegramClient(
                f'tucl_user_{user_id}',
                api_id or API_ID,
                api_hash or API_HASH
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                if not phone:
                    return 'NEED_PHONE'
                
                sent_code = await client.send_code_request(phone)
                self.login_attempts[user_id] = {
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent_code.phone_code_hash
                }
                return 'NEED_CODE'
                
            self.user_sessions[user_id] = client
            return client
            
        except Exception as e:
            self.logger.error(f"Errore login: {e}")
            return None

    async def setup_handlers(self):
        """Tutti gli handler originali del TUCL Bot"""

        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "👋 TUCL Bot - Tutte le funzioni attive!\n"
                "Comandi disponibili:\n"
                "/login - Accedi con le tue API\n"
                "/settings - Gestisci il bot\n"
                "/list_chats - Mostra le tue chat"
            )

        @self.client.on(events.NewMessage(pattern=r'/login (\d+) (\w+) (\+\d+)'))
        async def login_handler(event):
            user_id = event.sender_id
            api_id = int(event.pattern_match.group(1))
            api_hash = event.pattern_match.group(2)
            phone = event.pattern_match.group(3)
            
            result = await self.init_user_session(
                user_id=user_id,
                api_id=api_id,
                api_hash=api_hash,
                phone=phone
            )
            
            if result == 'NEED_CODE':
                await event.respond("📱 Codice inviato! Usa /verify_code XXXX")

        @self.client.on(events.NewMessage(pattern=r'/verify_code (\d+)'))
        async def verify_code_handler(event):
            user_id = event.sender_id
            code = event.pattern_match.group(1)
            
            if user_id not in self.login_attempts:
                await event.respond("❌ Prima esegui /login")
                return
                
            try:
                await self.login_attempts[user_id]['client'].sign_in(
                    phone=self.login_attempts[user_id]['phone'],
                    code=code,
                    phone_code_hash=self.login_attempts[user_id]['phone_code_hash']
                )
                await event.respond("✅ Login completato!")
            except SessionPasswordNeededError:
                await event.respond("🔐 Inserisci la password 2FA con /verify_2fa PASSWORD")
            except Exception as e:
                await event.respond(f"❌ Errore: {str(e)}")

        @self.client.on(events.NewMessage(pattern='/list_chats'))
        async def list_chats_handler(event):
            user_id = event.sender_id
            if user_id not in self.user_sessions:
                await event.respond("❌ Devi prima fare il login")
                return
                
            try:
                dialogs = await self.user_sessions[user_id].get_dialogs()
                response = "📚 Le tue chat:\n" + "\n".join(
                    f"{dialog.name}" for dialog in dialogs[:10]  # Limite a 10 chat
                )
                await event.respond(response)
            except Exception as e:
                await event.respond(f"❌ Errore: {str(e)}")

    async def run(self):
        """Loop principale con riconnessione automatica"""
        while True:
            try:
                self.client = TelegramClient('tucl_main', API_ID, API_HASH)
                await self.client.start(bot_token=BOT_TOKEN)
                
                await self.setup_handlers()
                self.logger.info("✅ Bot avviato con tutte le funzioni")
                await self.client.run_until_disconnected()
                
            except FloodWaitError as e:
                self.logger.warning(f"⏳ FloodWait: aspetta {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except RPCError as e:
                self.logger.error(f"🔌 Errore connessione: {str(e)}")
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.critical(f"💥 Errore: {str(e)}")
                await asyncio.sleep(30)

def run_webserver():
    """Web server minimale per health check"""
    @app.route('/')
    def home():
        return "🟢 TUCL Bot Online", 200
    app.run(host='0.0.0.0', port=8000)

async def main():
    bot = TUCLBot()
    Thread(target=run_webserver, daemon=True).start()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
