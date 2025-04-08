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
        # Database in-memory per sessioni
        self.user_sessions = {}  # {user_id: client}
        self.login_attempts = {}  # {user_id: {phone, code_hash, client}}
        self.limited_mode = False
        self.allowed_chats = set()
        
        # Configurazione logging per cloud
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s',
            handlers=[logging.StreamHandler()]
        )
        self.logger = logging.getLogger(__name__)

    async def safe_disconnect(self, client):
        """Disconnette un client in modo sicuro"""
        try:
            if client and client.is_connected():
                await client.disconnect()
            return True
        except Exception as e:
            self.logger.error(f"Disconnessione fallita: {e}")
            return False

    async def init_user_session(self, user_id, api_id=None, api_hash=None, phone=None, code=None, password=None):
        """Gestione completa del login con riconnessione"""
        try:
            # Pulisci sessioni esistenti
            if user_id in self.user_sessions:
                await self.safe_disconnect(self.user_sessions[user_id])
                del self.user_sessions[user_id]

            client = TelegramClient(
                f'tucl_user_{user_id}',
                api_id or API_ID,
                api_hash or API_HASH,
                connection_retries=3
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                if not phone:
                    return 'NEED_PHONE'
                
                sent_code = await client.send_code_request(phone)
                self.login_attempts[user_id] = {
                    'client': client,
                    'phone': phone,
                    'code_hash': sent_code.phone_code_hash,
                    'api_id': api_id,
                    'api_hash': api_hash
                }
                return 'NEED_CODE'
                
            self.user_sessions[user_id] = client
            return client
            
        except Exception as e:
            await self.safe_disconnect(client)
            self.logger.error(f"Login fallito per {user_id}: {e}")
            return None

    async def complete_login(self, user_id, code=None, password=None):
        """Completa il processo di login"""
        if user_id not in self.login_attempts:
            return None
            
        data = self.login_attempts[user_id]
        
        try:
            if code:
                await data['client'].sign_in(
                    phone=data['phone'],
                    code=code,
                    phone_code_hash=data['code_hash']
                )
            elif password:
                await data['client'].sign_in(password=password)
                
            self.user_sessions[user_id] = data['client']
            del self.login_attempts[user_id]
            return True
            
        except SessionPasswordNeededError:
            return 'NEED_2FA'
        except Exception as e:
            await self.safe_disconnect(data['client'])
            self.logger.error(f"Verifica fallita: {e}")
            return None

    async def setup_handlers(self):
        """Tutti gli handler del TUCL Bot originale"""

        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "🔧 **TUCL Bot - Menu**\n\n"
                "1. /login API_ID API_HASH +NUMERO\n"
                "2. /verify_code CODICE\n"
                "3. /verify_2fa PASSWORD\n"
                "4. /list_chats\n"
                "5. /settings"
            )

        @self.client.on(events.NewMessage(pattern=r'/login (\d+) (\w+) (\+\d+)'))
        async def login_handler(event):
            # Implementazione originale...

        @self.client.on(events.NewMessage(pattern=r'/verify_code (\d+)'))
        async def verify_code_handler(event):
            # Implementazione originale...

        @self.client.on(events.NewMessage(pattern=r'/verify_2fa (.+)'))
        async def verify_2fa_handler(event):
            # Implementazione originale...

        @self.client.on(events.NewMessage(pattern='/list_chats'))
        async def list_chats_handler(event):
            # Implementazione originale...

        @self.client.on(events.NewMessage(pattern='/settings'))
        async def settings_handler(event):
            buttons = [
                [Button.inline("🔒 Modalità Limitata", b"toggle_mode")],
                [Button.inline("📋 Chat Autorizzate", b"show_chats")]
            ]
            await event.respond("⚙️ **Impostazioni**:", buttons=buttons)

        @self.client.on(events.CallbackQuery(data=b"toggle_mode"))
        async def toggle_mode_handler(event):
            self.limited_mode = not self.limited_mode
            await event.respond(f"Modalità limitata: {'ON' if self.limited_mode else 'OFF'}")

    async def run_bot(self):
        """Loop principale con auto-healing"""
        while True:
            try:
                self.client = TelegramClient('tucl_main', API_ID, API_HASH)
                await self.client.start(bot_token=BOT_TOKEN)
                
                await self.setup_handlers()
                self.logger.info("✅ Bot fully operational")
                await self.client.run_until_disconnected()
                
            except FloodWaitError as e:
                self.logger.warning(f"⏳ FloodWait: pausing for {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except RPCError as e:
                self.logger.error(f"🔌 Connection error: {e}")
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.critical(f"💥 Critical error: {e}")
                await asyncio.sleep(30)
            finally:
                await self.safe_disconnect(self.client)

def run_webserver():
    """Web server per health checks"""
    @app.route('/')
    def home():
        return "🟢 TUCL Bot Online"
    
    @app.route('/ping')
    def ping():
        return "🏓 Pong", 200
        
    app.run(host='0.0.0.0', port=8000)

async def main():
    bot = TUCLBot()
    
    # Avvia web server in background
    Thread(target=run_webserver, daemon=True).start()
    
    try:
        await bot.run_bot()
    except KeyboardInterrupt:
        bot.logger.info("🛑 Manual shutdown")

if __name__ == '__main__':
    asyncio.run(main())
