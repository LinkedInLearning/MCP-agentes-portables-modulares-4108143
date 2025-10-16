# ===== Build slim =====
FROM python:3.12-slim AS base

# Seguridad y logs más previsibles
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependencias del sistema (opcionalmente instala ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependencias primero para cachear capas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código
COPY . .

# Expón el puerto del server
EXPOSE 8080

# No metas secretos en la imagen: AZURE_STORAGE_CONNECTION_STRING irá como secret/env en ACA
# Arranque del server (FastAPI + Streamable HTTP en /mcp)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
