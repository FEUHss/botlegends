# botlegends

## Coletor passivo do Market

O coletor Telethon é opcional e permanece desligado enquanto
`MARKET_COLLECTOR_ENABLED` não for `true`. Ele observa somente mensagens novas
do grupo/tópico configurados, não envia mensagens e não busca histórico.

Variáveis necessárias:

- `MARKET_COLLECTOR_ENABLED=true`
- `TELETHON_API_ID`
- `TELETHON_API_HASH`
- `TELETHON_SESSION` (StringSession; tratar como senha)
- `MARKET_CHAT_ID=-1003529877508`
- `MARKET_TOPIC_ID=67`

Para gerar a sessão localmente, configure `TELETHON_API_ID` e
`TELETHON_API_HASH` no terminal e execute:

```bash
python scripts/create_telethon_session.py
```

O banco guarda apenas o hash da mensagem e os preços extraídos. O texto
integral e a identidade do autor não são persistidos. Se a sessão ou qualquer
credencial estiver ausente, o coletor falha fechado e o bot principal continua
funcionando.
