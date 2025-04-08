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

# Configurazione da variabili d'ambiente (Railway le inietta automaticamente)
BOT_TOKEN = os.environ['BOT_TOKEN']
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']

# Inizializzazione app Flask
app = Flask(__name__)

class TUCLBot:
    def __init__(self):
        # Gestione sessioni in memoria
        self.user_sessions = {}
        self.login_attempts = {}
        self.limited_mode = False
        self.allowed_chats = set()
        
        # Configurazione logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    async def init_user_session(self, user_id, api_id=None, api_hash=None, phone=None, code=None, password=None):
        """Versione semplificata senza file di sessione"""
        try:
            client = TelegramClient(
                f'tucl_session_{user_id}',
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

    async def run_bot(self):
        """Loop principale con riconnessione automatica"""
        while True:
            try:
                async with TelegramClient('tucl_main', API_ID, API_HASH) as client:
                    # Handler comandi
                    @client.on(events.NewMessage(pattern='/start'))
                    async def start_handler(event):
                        await event.respond("🚀 TUCL Bot funzionante su Railway!")
                        
                    @client.on(events.NewMessage(pattern='/login'))
                    async def login_handler(event):
                        # ... (implementazione originale)
                        pass
                        
                    await client.start(bot_token=BOT_TOKEN)
                    self.logger.info("✅ Bot avviato")
                    await client.run_until_disconnected()
                    
            except FloodWaitError as e:
                self.logger.warning(f"⏳ FloodWait: aspetta {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except RPCError as e:
                self.logger.error(f"🔌 Errore connessione: {e}")
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.critical(f"💥 Errore: {e}")
                await asyncio.sleep(30)

def run_webserver():
    """Web server minimale per health check"""
    @app.route('/')
    def home():
        return "🟢 TUCL Bot Online", 200
    app.run(host='0.0.0.0', port=8000)

async def main():
    bot = TUCLBot()
    
    # Avvia web server in thread separato
    Thread(target=run_webserver, daemon=True).start()
    
    try:
        await bot.run_bot()
    except KeyboardInterrupt:
        self.logger.info("🛑 Arresto manuale")

if __name__ == '__main__':
    asyncio.run(main())
