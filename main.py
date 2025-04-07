import os
import json
import asyncio
import time
from dotenv import load_dotenv
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, PhoneNumberUnoccupiedError
from telethon.tl.functions.auth import LogOutRequest

load_dotenv()

class TUCLBot:
    def __init__(self):
        # Caricamento configurazione base
        self.bot_token = os.getenv("BOT_TOKEN")
        self.api_hash = os.getenv("API_HASH")
        self.api_id = int(os.getenv("API_ID"))
        
        # Configurazione directory sessioni
        os.makedirs('sessions', exist_ok=True)
        self.session_dir = 'sessions'
        
        # Inizializzazione client Telegram
        self.client = TelegramClient(f'{self.session_dir}/bot_session', self.api_id, self.api_hash)
        
        # Dati utenti e sessioni
        self.user_sessions = {}
        self.login_attempts = {}
        
        # Impostazioni
        self.limited_mode = False
        self.allowed_chats = set()
        
        # Carica le impostazioni all'avvio
        self.load_settings()

    # === GESTIONE IMPOSTAZIONI ===
    def load_settings(self):
        """Carica le impostazioni da file"""
        try:
            with open('tucl_settings.json', 'r') as f:
                data = json.load(f)
                self.limited_mode = data.get('limited_mode', False)
                self.allowed_chats = set(data.get('allowed_chats', []))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"⚠️ Impossibile caricare le impostazioni: {e}")
            # Valori di default
            self.limited_mode = False
            self.allowed_chats = set()

    def save_settings(self):
        """Salva le impostazioni su file"""
        try:
            with open('tucl_settings.json', 'w') as f:
                json.dump({
                    'limited_mode': self.limited_mode,
                    'allowed_chats': list(self.allowed_chats)
                }, f, indent=4)
        except Exception as e:
            print(f"⚠️ Errore salvataggio impostazioni: {e}")

    # === GESTIONE SESSIONI ===
    async def safe_disconnect(self, client):
        """Disconnette un client in modo sicuro"""
        try:
            if client and client.is_connected():
                await client(LogOutRequest())
                await client.disconnect()
            return True
        except Exception as e:
            print(f"Errore disconnessione: {e}")
            return False

    async def clean_user_sessions(self, user_id):
        """Pulisce tutte le sessioni per un utente specifico"""
        # Disconnette sessioni in memoria
        if user_id in self.user_sessions:
            await self.safe_disconnect(self.user_sessions[user_id])
            del self.user_sessions[user_id]
        
        if user_id in self.login_attempts:
            await self.safe_disconnect(self.login_attempts[user_id]['client'])
            del self.login_attempts[user_id]
        
        # Elimina file di sessione
        for filename in os.listdir(self.session_dir):
            if filename.startswith(f'tucl_user_session_{user_id}'):
                try:
                    os.remove(f'{self.session_dir}/{filename}')
                except Exception as e:
                    print(f"Errore eliminazione sessione {filename}: {e}")

    async def clean_all_sessions(self):
        """Pulisce tutte le sessioni esistenti"""
        # Disconnette sessioni attive
        for user_id in list(self.user_sessions.keys()):
            await self.clean_user_sessions(user_id)
        
        # Pulisce eventuali sessioni residue
        for filename in os.listdir(self.session_dir):
            if filename.startswith('tucl_user_session'):
                try:
                    os.remove(f'{self.session_dir}/{filename}')
                except Exception as e:
                    print(f"Errore eliminazione sessione {filename}: {e}")

    # === CORE FUNZIONALITÀ ===
    async def init_user_session(self, user_id, api_id=None, api_hash=None, phone=None, code=None, password=None):
        """Gestisce il processo di login completo"""
        await self.clean_user_sessions(user_id)
        
        if not all([api_id, api_hash, phone]):
            return None

        session_path = f'{self.session_dir}/tucl_user_session_{user_id}_{int(time.time())}'
        client = TelegramClient(session_path, api_id, api_hash)
        
        try:
            await client.connect()
            
            if not await client.is_user_authorized():
                sent_code = await client.send_code_request(phone)
                self.login_attempts[user_id] = {
                    'client': client,
                    'phone': phone,
                    'phone_code_hash': sent_code.phone_code_hash,
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'timestamp': time.time()
                }
                return 'NEED_CODE'
            
            self.user_sessions[user_id] = client
            return client
            
        except Exception as e:
            print(f"Errore inizializzazione sessione: {e}")
            await self.safe_disconnect(client)
            return None

    async def complete_login(self, user_id, code=None, password=None):
        """Completa il processo di login con codice o password 2FA"""
        if user_id not in self.login_attempts:
            return None
            
        data = self.login_attempts[user_id]
        client = data['client']
        
        try:
            if code:
                await client.sign_in(
                    phone=data['phone'],
                    code=code,
                    phone_code_hash=data['phone_code_hash']
                )
            elif password:
                await client.sign_in(password=password)
            
            self.user_sessions[user_id] = client
            del self.login_attempts[user_id]
            return client
            
        except SessionPasswordNeededError:
            return 'NEED_2FA'
        except Exception as e:
            print(f"Errore completamento login: {e}")
            await self.clean_user_sessions(user_id)
            return None

    # === HANDLERS ===
    def register_handlers(self):
        @self.client.on(events.NewMessage(pattern=r'/login (\d+) (\w+) (\+\d+)'))
        async def login_handler(event):
            user_id = event.sender_id
            if user_id in self.user_sessions:
                await event.respond("ℹ️ Usa /logout prima di un nuovo login")
                return
                
            try:
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
                    await event.respond("📱 Codice inviato. Inseriscilo con:\n/verify_code <codice>")
                elif isinstance(result, TelegramClient):
                    await event.respond("✅ Login automatico riuscito!")
                else:
                    await event.respond("❌ Errore durante il login")
            except Exception as e:
                await event.respond(f"❌ Errore: {str(e)}")

        @self.client.on(events.NewMessage(pattern=r'/verify_code (\d+)'))
        async def verify_code_handler(event):
            user_id = event.sender_id
            result = await self.complete_login(user_id=user_id, code=event.pattern_match.group(1))
            
            if result == 'NEED_2FA':
                await event.respond("🔐 Inserisci la password 2FA:\n/verify_2fa <password>")
            elif isinstance(result, TelegramClient):
                await event.respond("✅ Login completato! Usa /list_chats")
            else:
                await event.respond("❌ Codice non valido o errore")

        @self.client.on(events.NewMessage(pattern=r'/verify_2fa (.+)'))
        async def verify_2fa_handler(event):
            user_id = event.sender_id
            result = await self.complete_login(user_id=user_id, password=event.pattern_match.group(1))
            
            if isinstance(result, TelegramClient):
                await event.respond("✅ Accesso completato!")
            else:
                await event.respond("❌ Password errata o errore")

        @self.client.on(events.NewMessage(pattern='/logout'))
        async def logout_handler(event):
            user_id = event.sender_id
            await self.clean_user_sessions(user_id)
            await event.respond("✅ Tutte le tue sessioni sono state chiuse")

        @self.client.on(events.NewMessage(pattern='/clean_all'))
        async def clean_all_handler(event):
            if event.sender_id not in self.user_sessions:
                await event.respond("❌ Devi essere loggato come admin")
                return
                
            await self.clean_all_sessions()
            await event.respond("✅ Tutte le sessioni sono state ripulite")

        @self.client.on(events.NewMessage(pattern='/list_chats'))
        async def list_chats_handler(event):
            user_id = event.sender_id
            if user_id not in self.user_sessions:
                await event.respond("❌ Devi prima fare il login")
                return
                
            try:
                dialogs = await self.user_sessions[user_id].get_dialogs(limit=20)
                response = "🗂️ Le tue chat:\n" + "\n".join(
                    f"{i+1}. {dialog.name} (ID: {dialog.id})" 
                    for i, dialog in enumerate(dialogs) 
                    if dialog.is_channel or dialog.is_group
                )
                await event.respond(response or "⛔ Nessuna chat trovata")
            except Exception as e:
                await event.respond(f"❌ Errore: {str(e)}")

        @self.client.on(events.NewMessage(pattern='/settings'))
        async def settings_handler(event):
            buttons = [
                [Button.inline("🔒 Modalità Limitata", b"toggle_limited_mode")],
                [Button.inline("📋 Lista Chat Autorizzate", b"list_allowed_chats")]
            ]
            await event.respond(
                "⚙️ **Impostazioni TUCL Bot**\n\n"
                f"• Funzioni limitate: **{'ON' if self.limited_mode else 'OFF'}**\n"
                f"• Chat autorizzate: **{len(self.allowed_chats)}**",
                buttons=buttons
            )

        @self.client.on(events.CallbackQuery(data=b"toggle_limited_mode"))
        async def toggle_limited_mode(event):
            self.limited_mode = not self.limited_mode
            self.save_settings()
            await event.edit(
                f"✅ Modalità limitata: **{'ATTIVATA' if self.limited_mode else 'DISATTIVATA'}**\n\n"
                "In questa modalità:\n"
                "▶️ Risponde solo in chat autorizzate\n"
                "▶️ Tenta di uscire da gruppi non whitelistati"
            )

        @self.client.on(events.NewMessage(pattern=r'/allow_chat (.+)'))
        async def allow_chat_handler(event):
            chat_identifier = event.pattern_match.group(1).strip().lower()
            
            if chat_identifier.startswith('@'):
                self.allowed_chats.add(chat_identifier)
                await event.respond(f"✅ Chat {chat_identifier} autorizzata!")
            else:
                try:
                    chat_id = int(chat_identifier)
                    self.allowed_chats.add(chat_id)
                    await event.respond(f"✅ Chat ID {chat_id} autorizzata!")
                except ValueError:
                    await event.respond("❌ Formato non valido. Usa:\n`/allow_chat @username` o `/allow_chat 12345`")
            
            self.save_settings()

        @self.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.respond(
                "👋 TUCL Bot - Guida Completa\n\n"
                "🔹 **Login:**\n"
                "/login <api_id> <api_hash> <numero>\n"
                "/verify_code <codice>\n"
                "/verify_2fa <password>\n\n"
                "🔹 **Gestione:**\n"
                "/list_chats - Mostra le tue chat\n"
                "/logout - Chiudi la sessione\n"
                "/settings - Configura il bot\n"
                "/clean_all - [Admin] Ripulisci tutto\n\n"
                "⚠️ Per problemi di 'codice condiviso':\n"
                "1. Usa /logout\n"
                "2. Attendi 5 minuti\n"
                "3. Riprova il login"
            )

    # === AVVIO ===
    async def start(self):
        await self.client.start(bot_token=self.bot_token)
        self.register_handlers()
        print("🤖 Bot avviato correttamente!")
        print(f"🔒 Modalità limitata: {'ATTIVA' if self.limited_mode else 'DISATTIVATA'}")
        await self.client.run_until_disconnected()

if __name__ == '__main__':
    bot = TUCLBot()
    asyncio.run(bot.start())
