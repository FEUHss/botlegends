import asyncio
import getpass
import os
import subprocess
import sys
from pathlib import Path

# Carrega primeiro a copia limpa do Telethon. Usar Path dentro do Python
# evita a conversao incorreta de "Joao" em shells antigos do Windows.
work_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(work_root / "telethon-vendor"))

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(os.getenv("TELETHON_API_ID") or input("App api_id: ").strip())
    api_hash = os.getenv("TELETHON_API_HASH") or getpass.getpass("App api_hash: ").strip()
    phone = input("Número da conta Venus, com DDI: ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        await client.send_code_request(phone)
        code = input("Código recebido no Telegram: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as error:
            if type(error).__name__ != "SessionPasswordNeededError":
                raise
            password = getpass.getpass("Senha de duas etapas: ")
            await client.sign_in(password=password)

        me = await client.get_me()
        session_value = client.session.save()
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "Set-Clipboard"],
            input=session_value,
            text=True,
            check=True,
        )
        print(f"Sessão autorizada para: {me.first_name} (ID {me.id})")
        print("TELETHON_SESSION foi copiada para a área de transferência.")
        print("Não cole esse valor em chats, arquivos ou mensagens.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
