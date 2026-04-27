# Plan: Docker Deploy Guide for Home Server

**Spec:** `docs/superpowers/specs/2026-04-27-docker-deploy-guide-design.md`
**Branch:** `chore/deploy-guide-and-dockerignore`
**Base:** `develop` @ `d5aace9`

## Tasks

### Task 1: ampliar `.dockerignore`

**Goal:** Agregar entradas para artefactos de desarrollo.

**Files:**
- `.dockerignore`.

**Cambio:** agregar al final del archivo:

```
# Dev/test artifacts
tests/
docs/
requirements-dev.txt
pytest.ini
.pytest_cache/
```

**Verification:**

```
docker build .   (cuando VT-x est\u00e9 disponible)
```

No es ejecutable ahora; verificaci\u00f3n diferida al deploy real. Commit
sigue.

**Commit:** `ignore dev artifacts in docker build context`

---

### Task 2: agregar secci\u00f3n de deploy al README

**Goal:** Insertar una secci\u00f3n nueva "Deploy en home server (Ubuntu
Server)" entre la secci\u00f3n "Levantar el bot" y "Desarrollo local (sin
Docker)".

**Files:**
- `README.md`.

**Contenido a insertar** (despu\u00e9s del bloque que termina con
`docker compose down` y antes de `## Desarrollo local`):

```markdown
## Deploy en home server (Ubuntu Server)

Gu\u00eda paso a paso para correr el bot en un servidor Ubuntu con Docker
ya instalado.

### 1. Instalar git (si no est\u00e1 instalado)

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
# Opcional, descomentar solo si configur\u00e1s cookies (ver secci\u00f3n
# "Cookies de YouTube" m\u00e1s abajo)
# YTDL_COOKIES=/app/cookies/cookies.txt
```

Guardar (Ctrl+O, Enter, Ctrl+X).

### 4. Build y arrancar

```bash
sudo docker compose up -d --build
```

La primera vez tarda 3-5 minutos (descarga base image, instala ffmpeg y
deps de Python).

### 5. Verificar que est\u00e9 corriendo

```bash
sudo docker compose logs -f
```

Buscar en los logs:

```
ssj-bot: SSJ Bot conectado en N servidor(es).
```

Salir del log con Ctrl+C (eso no detiene el bot, solo el seguimiento).

### Operaci\u00f3n diaria

| Acci\u00f3n | Comando |
|--------|---------|
| Ver logs en vivo | `sudo docker compose logs -f` |
| Ver \u00faltimas 200 l\u00edneas | `sudo docker compose logs --tail=200` |
| Reiniciar el bot | `sudo docker compose restart` |
| Detener | `sudo docker compose down` |
| Actualizar a \u00faltima versi\u00f3n | `git pull && sudo docker compose up -d --build` |
| Estado del container | `sudo docker compose ps` |

> Nota: si tu user est\u00e1 en el grupo `docker`
> (`sudo usermod -aG docker $USER`), los `sudo` sobran. Requiere logout
> y login para que tome efecto.

### Cookies de YouTube (opcional)

Si en los logs ves errores tipo `LOGIN_REQUIRED` o
`Sign in to confirm your age`, agreg\u00e1 cookies de tu navegador:

1. En tu PC, exportar cookies de youtube.com en formato Netscape con la
   extensi\u00f3n
   [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).
2. Copiar el archivo al server:

   ```bash
   scp cookies.txt usuario@server:/ruta/a/ssj-bot/cookies/cookies.txt
   ```

3. En el server, descomentar la l\u00ednea `YTDL_COOKIES` en `.env`:

   ```dotenv
   YTDL_COOKIES=/app/cookies/cookies.txt
   ```

4. Reiniciar:

   ```bash
   sudo docker compose restart
   ```
```

**Verification:** abrir el README renderizado en GitHub o un viewer
markdown y validar que la nueva secci\u00f3n se ve bien y queda entre las
dos secciones existentes.

**Commit:** `add ubuntu server deploy guide to readme`

---

### Task 3: sanity check tests

**Goal:** confirmar que los cambios documentales no rompen tests.

**Verification:**

```
python -m pytest -q
```

Debe pasar 6/6.

**Commit:** ninguno.

## Acceptance Criteria

- `.dockerignore` con las nuevas entradas.
- README con la secci\u00f3n de deploy completa, posicionada correctamente.
- Tests 6/6 verdes.

## Out of Scope

- Cambios al Dockerfile o compose.
- `.env.example`, scripts de setup, multi-stage, healthcheck, CI/CD.
- Validar el build real en amd64 (diferido a cuando VT-x est\u00e9
  disponible o se haga el deploy real).
