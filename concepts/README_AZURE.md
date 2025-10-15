Despliegue (Azure) - conceptos/task_pilot_server y client_openai

Resumen:
- `task_pilot_server.py` ahora soporta almacenamiento en Azure Blob Storage (variables de entorno AZURE_STORAGE_ACCOUNT y AZURE_STORAGE_CONTAINER).
- Si no se configuran variables, el servidor usa `data/tasks.json` local como fallback (útil para desarrollo).
- `client_openai.py` mantiene el modo interactivo y añade un endpoint HTTP POST /message para recibir mensajes desde Azure Bot Service.

Variables de entorno relevantes:
- AZURE_STORAGE_ACCOUNT: nombre de la cuenta de Storage
- AZURE_STORAGE_CONTAINER: nombre del contenedor donde se guardará `tasks.json`
- AZURE_OPENAI_KEY / OPENAI_API_KEY: según tu configuración de OpenAI/Azure OpenAI (recomendado en Key Vault)

Recomendaciones de despliegue:
1. Crear Storage Account y Container:
   - az storage account create ...
   - az storage container create --name <container> --account-name <account>
2. Crear Managed Identity para las Container Apps / Containers y asignar el rol "Storage Blob Data Contributor" al scope del storage.
3. Desplegar imágenes en Azure Container Apps o ACI. Usa ACR para almacenar imágenes.
4. Configurar Key Vault para secretos (si necesitas claves) y otorgar acceso a las identidades gestionadas.

Construir y ejecutar localmente (desde carpeta `concepts`):

# Crear entorno virtual e instalar dependencias
python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt

# Ejecutar servidor localmente (modo desarrollo)
python task_pilot_server.py

# Ejecutar cliente interactivo
python client_openai.py task_pilot_server.py

# Ejecutar cliente en modo HTTP (usando uvicorn)
uvicorn client_openai:app --host 0.0.0.0 --port 8000

Notas de seguridad:
- No hardcodear keys en el repositorio. Usar Key Vault y Managed Identity en producción.
- Seguir las mejores prácticas de Azure (retries, logging, least privilege).
