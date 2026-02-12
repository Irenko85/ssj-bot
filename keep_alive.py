from flask import Flask
from threading import Thread
import logging
import os

# Configurar logger
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def home():
    return "SSJ Bot is alive! 🎵"


def run():
    """Ejecuta el servidor Flask en el puerto configurado (Render usa PORT)"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    """Inicia el servidor web en un thread daemon para mantener el bot vivo en Render"""
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Iniciando servidor web keep-alive para Render en puerto {port}...")
    server = Thread(target=run, daemon=True)
    server.start()
    logger.info(f"Servidor web iniciado en http://0.0.0.0:{port}")
