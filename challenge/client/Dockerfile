# Dockerfile (client)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Instala deps primero para cachear capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copia el código
COPY . .

# Expone el puerto de FastAPI
EXPOSE 8000

# Arranca la app del cliente (FastAPI + SPA)
# IMPORTANTE: ajusta el módulo si tu ruta cambia
CMD ["uvicorn", "chat_app.client_openai:app", "--host", "0.0.0.0", "--port", "8000"]