# SSJ Bot

Bot de música para Discord (YouTube via `yt-dlp` + `ffmpeg`). Pensado para correr en un servidor personal con Docker.

## Comandos principales

- `!play <url|búsqueda>` (alias `!p`) - reproduce o agrega a la cola
- `!skip` (alias `!s`) - salta la canción actual
- `!pause` / `!resume`
- `!queue` (alias `!q`) - muestra la cola
- `!shuffle` - mezcla la cola
- `!clear` (alias `!qc`) - vacía la cola
- `!rq <pos>` - elimina canción por posición
- `!stop` - detiene y desconecta
- `!search <query>` - busca y muestra menú de selección
- `!dbz` / `!anime` - playlists temáticas
- `!coin` - cara o sello

## Requisitos

- Docker y Docker Compose
- Token de bot de Discord ([Developer Portal](https://discord.com/developers/applications))

## Configuración

1. Copia tu token al archivo `.env`:

   ```dotenv
   DISCORD_TOKEN=tu_token
   GUILD_ID=id_de_tu_servidor
   LOG_LEVEL=INFO
   # Opcional: cookies de YouTube
   # YTDL_COOKIES=/app/cookies/cookies.txt
   ```

2. (Opcional) Si quieres usar cookies para evitar errores de YouTube (`LOGIN_REQUIRED`, throttling, contenido restringido):

   - Exporta tus cookies de YouTube en formato Netscape (extensión [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc))
   - Guárdalo en `./cookies/cookies.txt`
   - Descomenta `YTDL_COOKIES=/app/cookies/cookies.txt` en `.env`

   El volumen `./cookies` se monta en `/app/cookies` (read-only). El bot lo copia internamente a un directorio temporal escribible.

## Levantar el bot

```bash
docker compose up -d --build
```

Logs en vivo:

```bash
docker compose logs -f
```

Detener:

```bash
docker compose down
```

## Desarrollo local (sin Docker)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
python bot.py
```

Necesitas `ffmpeg` instalado en el PATH del sistema.

## Estructura

```
.
├── bot.py              # Entry point + carga de cogs
├── cogs/
│   └── music_cog.py    # Lógica de música, queue, voice
├── utils/
│   └── utils.py        # Helpers (playlists, limpieza de URLs)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
