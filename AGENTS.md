# Reglas del agente — ssj-bot

## Entorno virtual (OBLIGATORIO)

Este proyecto usa un entorno virtual ubicado en `.venv/`. Los binarios
`python`, `python3`, `pip`, `pytest` del sistema **NO deben usarse nunca**
directamente — no están disponibles o no tienen las dependencias instaladas.

### Regla de oro

**Antes de ejecutar cualquier comando Python, pytest u otro binario del
proyecto, busca el entorno virtual si no conoces la ruta exacta:**

```bash
find . -name "python" -path "*/.venv/*" | head -1
```

Una vez encontrado, úsalo siempre con ruta completa:

```bash
.venv/bin/python        # intérprete Python
.venv/bin/python -m pytest tests/ -v   # ejecutar tests
.venv/bin/pip install <paquete>        # instalar dependencias
```

### Rutas conocidas en este proyecto

| Binario   | Ruta                        |
|-----------|-----------------------------|
| Python    | `.venv/bin/python`          |
| pytest    | `.venv/bin/python -m pytest`|
| pip       | `.venv/bin/pip`             |

### Verificación de tests

Siempre correr la suite completa después de cualquier cambio:

```bash
.venv/bin/python -m pytest tests/ -v
```

Resultado esperado: todos los tests en `PASSED`. Si alguno falla, reportarlo
antes de declarar el trabajo completo.

## Stack del proyecto

- **Lenguaje:** Python 3.12+
- **Framework:** discord.py (bot de Discord)
- **Audio:** yt-dlp + ffmpeg
- **Tests:** pytest
- **Contenedor:** Docker (producción)

## Convenciones

- No introducir dependencias nuevas sin listarlas explícitamente.
- No modificar `requirements.txt` sin justificación.
- Respetar el estilo de código existente (sin reformatear archivos no tocados).
- Los mensajes de commit van en inglés, máx. ~50 caracteres, sin emojis.
