# Docker Deploy Guide for Home Server

**Date:** 2026-04-27
**Branch:** `chore/deploy-guide-and-dockerignore`
**Type:** Chore / Documentation

## Goal

Dejar la infraestructura Docker existente lista para deploy en un home
server Ubuntu Server, con una guía clara dentro del README que permita al
usuario clonar, configurar y levantar el bot en pocos pasos.

## Context

El repo ya tiene:

- `Dockerfile` (python:3.12-slim, single-stage, ffmpeg + libopus, user
  no-root, `CMD python -u bot.py`).
- `docker-compose.yml` (env_file, volumen `./cookies` ro, restart
  unless-stopped, log rotation).
- `.dockerignore` razonable (cubre `__pycache__`, `.env`, cookies, venv).
- `README.md` con sección Docker básica y comandos de operación.

Lo que falta:

1. `.dockerignore` no excluye carpetas de desarrollo recientes
   (`tests/`, `docs/`, `requirements-dev.txt`, `pytest.ini`,
   `.pytest_cache/`).
2. README no documenta el flujo concreto de deploy en un Ubuntu Server
   pelado (instalar git, clonar, crear `.env`, levantar, operar,
   actualizar).

## Non-Goals

- No CI/CD (GitHub Actions, registry).
- No multi-stage build.
- No healthcheck.
- No `.env.example`.
- No cookies de YouTube en el primer deploy (se agregan después si hay
  errores LOGIN_REQUIRED).
- No cambios al `Dockerfile` ni a `docker-compose.yml`.

## Approach

### Cambio 1: ampliar `.dockerignore`

Agregar al archivo existente:

```
# Dev/test artifacts
tests/
docs/
requirements-dev.txt
pytest.ini
.pytest_cache/
```

Esto reduce el contexto del build y evita que cambios futuros en el
Dockerfile (ej. un `COPY . .` accidental) filtren archivos de desarrollo.

### Cambio 2: agregar sección "Deploy en home server (Ubuntu Server)" al README

Estructura de la nueva sección:

1. **Pre-requisitos** (Docker + Compose ya instalados; falta git).
2. **Instalar y configurar git** — `sudo apt update && sudo apt install -y git`.
3. **Clonar el repo** — `git clone <url> && cd ssj-bot`.
4. **Crear `.env`** — `nano .env` con contenido mostrado inline.
5. **Build y arrancar** — `sudo docker compose up -d --build`.
6. **Verificar** — `sudo docker compose logs -f`, esperar "SSJ Bot
   conectado en N servidor(es)".
7. **Operación** — tabla con comandos comunes:
   - Ver logs en vivo
   - Reiniciar
   - Detener
   - Actualizar a la última versión (git pull + rebuild)
8. **Cookies de YouTube (opcional)** — qué hacer si aparece
   LOGIN_REQUIRED en logs (exportar cookies, scp al server, descomentar
   en `.env`).

La sección se posiciona después de la sección "Levantar el bot" y antes
de "Desarrollo local (sin Docker)".

## Risks

- **Guía amarrada a comandos `sudo docker`:** asumimos que el usuario no
  agregó su user al grupo `docker`. Si lo hizo, los `sudo` sobran pero no
  rompen nada. Mencionarlo como nota.
- **`apt install git` puede no aplicar** si la distro no es Ubuntu o si
  ya está instalado. La guía dice "instalar si falta", `apt install -y`
  es idempotente.
- **`.dockerignore` que oculte algo necesario:** los paths agregados
  (tests, docs, requirements-dev, pytest.ini, .pytest_cache) no son
  copiados por el Dockerfile actual, así que el riesgo es cero.

## Acceptance Criteria

1. `.dockerignore` actualizado con las nuevas entradas.
2. README contiene la sección de deploy con todos los pasos
   reproducibles en Ubuntu Server.
3. Sin cambios al Dockerfile ni compose.
4. Tests siguen pasando (sanity check, aunque no toca código).
