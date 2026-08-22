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

O banco guarda o hash, os preços extraídos e, por até 7 dias, o texto da
mensagem para diagnóstico do parser no painel privado. A identidade do autor
não é persistida. Depois de 7 dias, o texto é limpo automaticamente e os dados
estruturados de preço permanecem. Se a sessão ou qualquer credencial estiver
ausente, o coletor falha fechado e o bot principal continua funcionando.

