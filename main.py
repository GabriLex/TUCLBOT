import asyncio
import logging
from threading import Thread
from flask import Flask
from telethon import TelegramClient, events
from telethon.errors import (
    RPCError, FloodWaitError,
    SessionPasswordNeededError,
    PhoneNumberUnoccupiedError
)

# Configurazione da variabili d'ambiente (Render le inietta automaticamente)
import os
BOT_TOKEN = os.environ['BOT_TOKEN']
API_ID = int(os.environ['API_ID'])
API_HASH = os.environ['API_HASH']

# Inizializzazione app Flask
app = Flask(__name__)

class TUCLBot:
    def __init__(self):
        # Stato connessione
        self.client = None
        self.is_connected = False
        
        # Configurazione logging per Render
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()  # Log su stdout (obbligatorio per Render)
            ]
        )
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Connessione con gestione errori specifica per Render"""
        try:
            self.client = TelegramClient(
                'tucl_session',
                API_ID,
                API_HASH,
                connection_retries=None
            )
            
            await self.client.start(bot_token=BOT_TOKEN)
            self.is_connected = True
            self.logger.info("✅ Connesso a Telegram")
            return True
            
        except RPCError as e:
            self.logger.error(f"Errore RPC: {str(e)}")
            return False
        except Exception as e:
            self.logger.critical(f"Errore connessione: {str(e)}")
            return False

    async def setup_handlers(self):
        """Configurazione handler per Render"""
        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond("🚀 TUCL Bot attivo su Render!")
            
        @self.client.on(events.NewMessage(pattern='/ping'))
        async def ping_handler(event):
            await event.respond("🏓 Pong! Connessione stabile")

    async def run(self):
        """Loop principale ottimizzato per Render"""
        while True:
            if not self.is_connected:
                if not await self.connect():
                    self.logger.info("🔄 Tentativo di riconnessione tra 10s...")
                    await asyncio.sleep(10)
                    continue
                    
                await self.setup_handlers()
                
            try:
                self.logger.info("🤖 In ascolto di messaggi...")
                await self.client.run_until_disconnected()
                
            except (FloodWaitError, RPCError) as e:
                wait_time = e.seconds if hasattr(e, 'seconds') else 15
                self.logger.warning(f"⏳ Disconnessione temporanea. Riprovo tra {wait_time}s...")
                self.is_connected = False
                await asyncio.sleep(wait_time)
            except Exception as e:
                self.logger.error(f"💥 Errore runtime: {str(e)}")
                self.is_connected = False
                await asyncio.sleep(30)

def run_webserver():
    """Web server minimale per health check"""
    @app.route('/')
    def home():
        return "🟢 TUCL Bot Online", 200
        
    @app.route('/ping')
    def ping():
        return "🏓 Pong", 200
        
    app.run(host='0.0.0.0', port=8000)

async def main():
    bot = TUCLBot()
    
    # Avvia web server in thread separato
    Thread(target=run_webserver, daemon=True).start()
    bot.logger.info("🌐 Web server avviato su porta 8000")
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        bot.logger.info("🛑 Arresto manuale")

if __name__ == '__main__':
    asyncio.run(main())
