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

## Deploy en home server (Ubuntu Server)

Guía paso a paso para correr el bot en un servidor Ubuntu con Docker ya instalado.

### 1. Instalar git (si no está instalado)

```bash
sudo apt update
sudo apt install -y git
```

Verificar: `git --version`.

### 2. Clonar el repo

```bash
git clone https://github.com/Irenko85/ssj-bot.git
cd ssj-bot
```

### 3. Crear archivo `.env`

```bash
nano .env
```

Pegar el siguiente contenido y reemplazar el token por el real:

```dotenv
DISCORD_TOKEN=tu_token_real_aqui
LOG_LEVEL=INFO
# Opcional, descomentar solo si configurás cookies (ver sección
# "Cookies de YouTube" más abajo)
# YTDL_COOKIES=/app/cookies/cookies.txt
```

Guardar (Ctrl+O, Enter, Ctrl+X).

### 4. Build y arrancar

```bash
sudo docker compose up -d --build
```

La primera vez tarda 3-5 minutos (descarga base image, instala ffmpeg y deps de Python).

### 5. Verificar que esté corriendo

```bash
sudo docker compose logs -f
```

Buscar en los logs:

```
ssj-bot: SSJ Bot conectado en N servidor(es).
```

Salir del log con Ctrl+C (eso no detiene el bot, solo el seguimiento).

### Operación diaria

| Acción | Comando |
|--------|---------|
| Ver logs en vivo | `sudo docker compose logs -f` |
| Ver últimas 200 líneas | `sudo docker compose logs --tail=200` |
| Reiniciar el bot | `sudo docker compose restart` |
| Detener | `sudo docker compose down` |
| Actualizar a última versión | `git pull && sudo docker compose up -d --build` |
| Estado del container | `sudo docker compose ps` |

> Nota: si tu user está en el grupo `docker` (`sudo usermod -aG docker $USER`), los `sudo` sobran. Requiere logout y login para que tome efecto.

### Cookies de YouTube (opcional)

Si en los logs ves errores tipo `LOGIN_REQUIRED` o `Sign in to confirm your age`, agregá cookies de tu navegador:

1. En tu PC, exportar cookies de youtube.com en formato Netscape con la extensión [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).
2. Copiar el archivo al server:

   ```bash
   scp cookies.txt usuario@server:/ruta/a/ssj-bot/cookies/cookies.txt
   ```

3. En el server, descomentar la línea `YTDL_COOKIES` en `.env`:

   ```dotenv
   YTDL_COOKIES=/app/cookies/cookies.txt
   ```

4. Reiniciar:

   ```bash
   sudo docker compose restart
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
