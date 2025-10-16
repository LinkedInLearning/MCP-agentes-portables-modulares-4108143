# Despliegue del **Cliente (FastAPI + SPA)** en **Azure Container Apps** — *Challenge Edition* 🎯

Este README te guía para desplegar **tu cliente** (FastAPI + SPA) en **Azure Container Apps (ACA)** y probar el flujo extremo a extremo contra tu **servidor MCP (Streamable HTTP)**. Al final hay un **challenge**: añadir una **nueva tool** al servidor y **redeplegar**.

---

## 0) Estructura mínima del proyecto

```
challenge/
├─ server/
│  ├─ main.py                   # expone POST /mcp (streamable_http_app)
│  ├─ task_pilot_server.py      # tu MCP con Azure Blob (STORE, tools, resources)
│  ├─ requirements.txt
│  └─ Dockerfile                # (server) - ya lo tienes
└─ client/
   ├─ chat_app/
   │  └─ client_openai.py       # FastAPI con / y /message (usa MCP_SERVER_URL)
   ├─ static/
   │  └─ chat.html              # Tu SPA (contenido a tu elección)
   ├─ requirements.txt
   └─ Dockerfile                # (client) - lo definimos aquí
```

> **Nota:** el cliente sirve la SPA desde `/static` y el HTML principal desde `/`. El endpoint que usa el bot/SPA es `/message`.

---

## 1) Requisitos previos

- **Azure CLI** y la extensión de **Container Apps**
  ```bash
  az upgrade
  az extension add -n containerapp --upgrade
  ```
- **Docker** instalado y en ejecución.
- Selecciona la **suscripción** de Azure:
  ```bash
  az login
  az account set --subscription "<TU_SUBSCRIPCION>"
  ```

---

## 2) Variables comunes

```bash
# Infra
RG="rg-mcp-demo"
LOC="westeurope"
ENV="env-mcp"

# Nombres de apps
SERVER_APP="mcp-server"
CLIENT_APP="mcp-client"

# Crea RG y env si aún no existen
az group create -n $RG -l $LOC
az containerapp env create -g $RG -n $ENV -l $LOC
```

> Se asume que ya desplegaste el **server** y tienes su FQDN. Si no, primero despliega `/server`.

Obtén el FQDN del **server**:
```bash
SERVER_FQDN=$(az containerapp show -g $RG -n $SERVER_APP --query "properties.configuration.ingress.fqdn" -o tsv)
echo "Server MCP: https://$SERVER_FQDN/mcp"
```

---

## 3) `Dockerfile` del **cliente** (FastAPI + SPA)

Crea `client/Dockerfile`:

```dockerfile
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
```

### `client/requirements.txt` (ejemplo mínimo)
Incluye tus libs reales. Como guía:

```
fastapi
uvicorn[standard]
python-dotenv
httpx
openai
mcp[cli]
```

### `.dockerignore` (recomendado)
Crea `client/.dockerignore`:

```
.venv
__pycache__
*.pyc
.env
.git
.gitignore
```

---

## 4) Despliegue del **cliente** en Azure Container Apps

### Con ACR (build/push) + `create`/`update`

```bash
ACR="acrmcpexample"
az acr create -g $RG -n $ACR --sku Basic
az acr login -n $ACR

# Desde client/
docker build -t $ACR.azurecr.io/mcp-client:1 .
docker push $ACR.azurecr.io/mcp-client:1

az containerapp create \
  -g $RG -n $CLIENT_APP \
  --environment $ENV \
  --image $ACR.azurecr.io/mcp-client:1 \
  --registry-server $ACR.azurecr.io \
  --ingress external --target-port 8000

az containerapp update -g $RG -n $CLIENT_APP \
  --set-env-vars \
    MCP_SERVER_URL="https://$SERVER_FQDN/mcp" \
    AZURE_OPENAI_ENDPOINT="https://<tu-endpoint>.openai.azure.com/" \
    AZURE_OPENAI_API_KEY="<tu_api_key>" \
    OPENAI_API_VERSION="2024-12-01-preview"
```

---

## 5) Pruebas rápidas ✅

### 5.1 Verifica el **servidor**
```bash
# /mcp existe (405 es correcto: requiere POST)
curl -i https://$SERVER_FQDN/mcp
```

### 5.2 Verifica el **cliente**
```bash
# Salud del cliente (si sirve la SPA en / te devolverá HTML)
curl -I https://$CLIENT_FQDN/

# Prueba el endpoint /message
curl -s -X POST https://$CLIENT_FQDN/message \
  -H "Content-Type: application/json" \
  -d '{"text":"Añade una tarea de prueba"}'
```

### 5.3 Logs en vivo
```bash
az containerapp logs show -g $RG -n $SERVER_APP --follow
az containerapp logs show -g $RG -n $CLIENT_APP --follow
```

---

## 6) **Challenge** 🧩 — Añade una **nueva Tool** al servidor y redepliega

### 6.1 Objetivo
- Añadir una tool **útil** al servidor MCP (por ejemplo, **`count_tasks`** para devolver el número de tareas).
- Redeplegar el **server** y comprobar que el cliente la descubre y la usa.

### 6.2 Cambios en `server/task_pilot_server.py`
Añade esto junto al resto de tools:

```python
@mcp.tool()
def count_tasks() -> int:
    """Return the total number of tasks stored."""
    return len(STORE)
```

> Alternativas: `search_tasks(query: str) -> list[Task]`, `rename_task(task_id: str, new_title: str) -> Task`, etc.

### 6.3 Redeploy del servidor

**Opción con ACR:**
```bash
# build + push nueva imagen
docker build -t $ACR.azurecr.io/mcp-server:2 ./server
docker push $ACR.azurecr.io/mcp-server:2

# actualiza la app a la nueva imagen
az containerapp update \
  -g $RG -n $SERVER_APP \
  --image $ACR.azurecr.io/mcp-server:2
```

### 6.4 Verificación de la nueva tool

- El cliente invoca `initialize()` + `list_tools()` en cada sesión: debería detectar `count_tasks`.
- Realiza una petición que fuerce el uso de la tool:

```bash
curl -s -X POST https://$CLIENT_FQDN/message \
  -H "Content-Type: application/json" \
  -d '{"text":"¿Cuántas tareas hay ahora mismo?"}'
```

Deberías ver que el modelo invoca `count_tasks` y responde con el número actual.

---

## 7) Troubleshooting

- **Ruta /mcp**: el server expone **POST `/mcp`**. Asegúrate de que `MCP_SERVER_URL` termina en `/mcp`.
- **IPv4/IPv6**: en local usa `127.0.0.1` si tienes problemas con `localhost`.
- **Blob inicial**: si el server lee el STORE en import y no existe el blob, crea el container/blob o añade un **fallback** (p. ej. `{}` por defecto) para evitar fallos de arranque.
- **Secrets**: no guardes la connection string en texto plano; usa `secretref:` en ACA.
- **CORS**: innecesario si la SPA vive en el mismo Container App. Si separas front y back, habilita CORS en FastAPI.

---

## 8) Limpieza (opcional)

```bash
az group delete -n $RG --yes --no-wait
```

---

### ✅ Entregables del Challenge
1. **Cliente** desplegado en ACA, apuntando a `MCP_SERVER_URL=https://<FQDN_SERVER>/mcp`.
2. **Nueva tool** en el server (p. ej., `count_tasks`) y **redeploy** realizado.
3. **Pruebas** con `curl` o desde la SPA confirmando que la tool está disponible y funciona.
