# MCP Inspector


El script client_llm.py implementa un cliente que conecta un modelo de lenguaje (LLM, como OpenAI GPT) con un servidor MCP (Model Context Protocol) para gestionar tareas mediante herramientas automatizadas. Aquí tienes una explicación por partes:

### 1. Importaciones y configuración
- Importa módulos estándar (`asyncio`, `json`, `os`, `sys`) y dependencias externas (`dotenv`, `openai`, `mcp`).
- Carga variables de entorno, como la clave de OpenAI y el modelo a usar.

### 2. Utilidades
- `_tool_def_for_openai`: Convierte la definición de una herramienta MCP al formato que espera OpenAI para funciones.
- `_extract_text_or_json_as_text`: Extrae el contenido de la respuesta MCP y lo devuelve como texto o JSON serializado.

### 3. Instrucciones del sistema
- Define un mensaje de sistema para el agente, indicando que puede gestionar tareas usando herramientas.

### 4. Clase principal: `TaskPilotAgent`
- **Inicialización**: Prepara la conexión al servidor MCP y al modelo OpenAI.
- **Contexto asíncrono**: Abre y cierra la conexión al servidor MCP usando generadores asíncronos.
- **list_tools_for_openai**: Obtiene la lista de herramientas disponibles en el servidor MCP y las adapta para OpenAI.
- **call_mcp_tool**: Ejecuta una herramienta en el servidor MCP y devuelve el resultado como texto.
- **chat**: Gestiona una conversación con el modelo de lenguaje, permitiendo que el modelo solicite la ejecución de herramientas MCP y reciba sus resultados, repitiendo el proceso hasta un máximo de iteraciones.

### 5. Ejecución principal
- Define un prompt inicial (o lo toma de los argumentos de línea de comandos).
- Muestra las herramientas disponibles.
- Envía el prompt al agente y muestra la respuesta final.

### 6. Uso
- El script se ejecuta con `python client_llm.py` y permite interactuar con el sistema de tareas usando lenguaje natural, aprovechando tanto el modelo de lenguaje como las herramientas MCP.



## Guion para vídeo explicativo: client_llm.py

### 1. ¿Qué es este script?
Este script permite que un agente de inteligencia artificial interactúe con un sistema de gestión de tareas, usando herramientas automatizadas y lenguaje natural. Utiliza la API de OpenAI y un servidor MCP para ejecutar acciones.

---

### 2. Importaciones y configuración
Primero, el script importa librerías necesarias:
- `asyncio` para programación asíncrona.
- `json`, `os`, `sys` para utilidades estándar.
- `dotenv` para cargar variables de entorno.
- `openai` para interactuar con el modelo de lenguaje.
- `mcp` para comunicarse con el servidor MCP.

Luego, carga la clave de OpenAI y el modelo a usar desde el archivo `.env`.

---

### 3. Funciones utilitarias
- `_tool_def_for_openai`: Convierte la definición de una herramienta MCP al formato que espera OpenAI.
- `_extract_text_or_json_as_text`: Extrae el contenido de la respuesta MCP y lo devuelve como texto o JSON.

---

### 4. Instrucciones del sistema
Define un mensaje de sistema para el agente, indicando que puede gestionar tareas usando herramientas.

---

### 5. Clase principal: `TaskPilotAgent`
Esta clase es el núcleo del script:
- **Inicialización**: Prepara la conexión al servidor MCP y al modelo OpenAI.
- **Contexto asíncrono**: Abre y cierra la conexión al servidor MCP.
- **list_tools_for_openai**: Obtiene la lista de herramientas disponibles en el servidor MCP y las adapta para OpenAI.
- **call_mcp_tool**: Ejecuta una herramienta en el servidor MCP y devuelve el resultado.
- **chat**: Gestiona una conversación con el modelo de lenguaje, permitiendo que el modelo solicite la ejecución de herramientas MCP y reciba sus resultados.

---

### 6. Ejecución principal
En la función `main`:
- Se define un prompt inicial, o se toma de los argumentos de línea de comandos.
- Se muestra la lista de herramientas disponibles.
- Se envía el prompt al agente y se imprime la respuesta final.

---

### 7. ¿Cómo se usa?
Se ejecuta con `python client_llm.py`. El usuario puede pedir al agente que cree tareas, las liste, o realice otras acciones usando lenguaje natural.

---

### 8. Resumen
Este script es un ejemplo de cómo combinar inteligencia artificial y automatización para gestionar tareas de manera eficiente y flexible.



## 1. **Propósito general**
El script conecta un modelo de lenguaje (LLM, usando Azure OpenAI) con un servidor MCP (Model Context Protocol), permitiendo que el modelo gestione tareas y utilice herramientas externas de forma automatizada.

---

## 2. **Integración con MCP**

### a. **Inicialización y conexión**
- Se usa la clase `ClientSession` de MCP para establecer una sesión con el servidor MCP, que se ejecuta como un proceso hijo usando `StdioServerParameters` y `stdio_client`.
- El método `__aenter__` de `TaskPilotAgent` crea el proceso del servidor MCP y abre la sesión, gestionando los recursos con `AsyncExitStack` para asegurar el cierre correcto.

```python
params = StdioServerParameters(
    command=sys.executable,
    args=["-u", server_path],
    env=None,
)
read, write = await self._stack.enter_async_context(stdio_client(params))
self.session = await self._stack.enter_async_context(ClientSession(read, write))
await self.session.initialize()
```
- Aquí, `read` y `write` son los canales de comunicación con el proceso MCP.

### b. **Listado de herramientas MCP**
- El método `list_tools_for_openai` consulta al servidor MCP por las herramientas disponibles (`self.session.list_tools()`), y las adapta al formato que espera OpenAI para funciones.

```python
tools = await self.session.list_tools()
return [_tool_def_for_openai(t.name, t.description, t.inputSchema) for t in tools.tools]
```
- Cada herramienta MCP tiene un nombre, descripción y un esquema de entrada (inputSchema) que describe los parámetros que acepta.

### c. **Ejecución de herramientas MCP**
- El método `call_mcp_tool` permite ejecutar una herramienta MCP por nombre, pasando los argumentos requeridos. El resultado se procesa y se convierte en texto o JSON para que el LLM lo pueda entender.

```python
result = await self.session.call_tool(name, arguments=args)
return _extract_text_or_json_as_text(result)
```
- El resultado puede ser texto, JSON, o una mezcla, y se normaliza para que el modelo lo procese correctamente.

---

## 3. **Llamadas a OpenAI y manejo de tools**

### a. **Preparación de mensajes y tools**
- Antes de interactuar con el modelo, se prepara la lista de herramientas en el formato OpenAI y los mensajes de la conversación (system, user).

```python
tools = await self.list_tools_for_openai()
messages = [
    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
    {"role": "user", "content": user_prompt},
]
```

### b. **Primera llamada al modelo**
- Se realiza una llamada a OpenAI usando el método `chat.completions.create`, pasando los mensajes y la lista de herramientas.

```python
response = await self.openai.chat.completions.create(
    model=self.model,
    messages=messages,
    tools=tools,
    tool_choice="auto",
)
```
- El modelo puede decidir si responde directamente o si solicita la ejecución de una herramienta (tool call).

### c. **Procesamiento de tool calls**
- Si el modelo solicita una tool call, el script la ejecuta en MCP y añade el resultado a la conversación.

```python
if response_message.tool_calls:
    for tool_call in response_message.tool_calls:
        result = await self.call_mcp_tool(
            tool_call.function.name,
            args=json.loads(tool_call.function.arguments),
        )
        messages.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": tool_call.function.name,
            "content": result,
        })
```
- Así, el modelo puede recibir información actualizada o realizar acciones en el sistema MCP.

### d. **Segunda llamada al modelo**
- Se realiza una segunda llamada a OpenAI, ahora con los resultados de las herramientas, para obtener la respuesta final del agente.

```python
final_response = await self.openai.chat.completions.create(
    model=self.model,
    messages=messages,
    tools=tools,
    tool_choice="none",
)
```
- El modelo puede ahora dar una respuesta informada, basada en los datos obtenidos por las herramientas MCP.

---

## 4. **Resumen del flujo**
1. El usuario envía un prompt.
2. El modelo decide si necesita usar una herramienta MCP.
3. Si es así, el script ejecuta la herramienta y le pasa el resultado al modelo.
4. El modelo responde al usuario, integrando los datos obtenidos.

---

## 5. **Ventajas de este enfoque**
- Permite que el LLM no solo converse, sino que actúe sobre un sistema real (MCP) usando herramientas especializadas.
- El modelo puede encadenar acciones, consultar datos, crear tareas, etc., todo de forma automatizada y conversacional.

----------------------------

### Function Calling Corriente (OpenAI)
- **Qué es:** Permite que el modelo de lenguaje solicite la ejecución de funciones definidas en el backend, usando un esquema JSON para los parámetros.
- **Cómo funciona:** El modelo genera una “tool call” (petición de función), el backend ejecuta la función localmente y devuelve el resultado al modelo.
- **Limitación:** Las funciones suelen estar definidas y ejecutadas en el mismo proceso o servidor donde corre el modelo, y su gestión es directa y limitada al entorno local.

---

### MCP (Model Context Protocol)
- **Qué es:** Es un protocolo y arquitectura para conectar modelos de lenguaje con sistemas externos y herramientas modulares, usando una comunicación estandarizada (por ejemplo, vía streams o sockets).
- **Cómo funciona:** El modelo solicita herramientas, pero estas pueden estar en otros procesos, servidores, o incluso en otros lenguajes. MCP gestiona la comunicación, la serialización de datos y la ejecución remota de herramientas.
- **Ventajas:** Permite desacoplar el modelo de las herramientas, escalar, distribuir, y reutilizar componentes. Las herramientas MCP pueden ser actualizadas, reemplazadas o ejecutadas en diferentes entornos sin modificar el modelo.

---

### Resumen Visual

| Aspecto                | Function Calling Corriente | MCP (Model Context Protocol)      |
|------------------------|---------------------------|-----------------------------------|
| Ejecución de funciones | Local, en el backend      | Remota, modular, distribuida      |
| Comunicación           | Directa, interna          | Protocolizada, vía streams/sockets|
| Escalabilidad          | Limitada                  | Alta, permite microservicios      |
| Flexibilidad           | Baja                      | Alta, herramientas intercambiables|
| Independencia          | Funciones acopladas       | Herramientas desacopladas         |

---

**Ejemplo:**  
- En OpenAI function calling, el modelo puede llamar a `get_weather(city)` y el backend ejecuta esa función localmente.
- Con MCP, el modelo puede pedir `get_weather(city)`, pero MCP puede enviar esa petición a un microservicio externo, recibir la respuesta y devolverla al modelo, todo de forma transparente.

---

**En resumen:**  
MCP es una capa de abstracción y comunicación que permite que los modelos de lenguaje usen herramientas externas de forma más flexible, escalable y desacoplada que el function calling tradicional.


---

### 1. **Manejo de errores robusto**
- Añade try/except en las llamadas a OpenAI y MCP para capturar y registrar errores de red, autenticación, parsing, etc.
- Devuelve mensajes claros al usuario en caso de fallo.

### 2. **Bucle de tool calls**
- Permite que el modelo encadene varias llamadas a herramientas (tool calls) en vez de solo una ronda. Usa un bucle con límite de iteraciones para evitar bucles infinitos.

### 3. **Validación de entorno**
- Verifica que todas las variables de entorno necesarias (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_CHAT_DEPLOYMENT`) estén presentes antes de ejecutar.

### 4. **Logging estructurado**
- Sustituye los `print` por el módulo `logging` para mejor control y registro de eventos y errores.

### 5. **Configuración flexible**
- Permite configurar parámetros (modelo, endpoint, script de servidor) por argumentos de línea de comandos o archivo de configuración, no solo por variables de entorno.

### 6. **Tipado y documentación**
- Añade anotaciones de tipo en todos los métodos y variables.
- Expande los docstrings para explicar el propósito y los parámetros de cada función.

### 7. **Modularización**
- Separa las utilidades (`tool_def_for_openai`, `extract_text_or_json_as_text`) y la clase principal en módulos distintos si el archivo crece.

### 8. **Sanitización de entrada**
- Valida y limpia el `user_prompt` antes de enviarlo al modelo.

### 9. **Recursos y cierre**
- Asegúrate de cerrar correctamente todos los recursos, incluso en caso de excepción (ya usas `AsyncExitStack`, lo cual es bueno).

### 10. **Pruebas y cobertura**
- Añade tests unitarios para las utilidades y mocks para las llamadas a MCP/OpenAI.


---

### 1. **Manejo de errores robusto**

```python
import logging

# Al inicio del script
logging.basicConfig(level=logging.INFO)

# Ejemplo en el método chat
try:
    response = await self.openai.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
except Exception as e:
    logging.error(f"OpenAI API error: {e}")
    return "Sorry, there was an error communicating with the language model."

# Similar para MCP
try:
    result = await self.call_mcp_tool(
        tool_call.function.name,
        args=json.loads(tool_call.function.arguments),
    )
except Exception as e:
    logging.error(f"MCP tool error: {e}")
    result = "Error executing tool."
```

---

### 2. **Bucle de tool calls (encadenamiento)**

```python
MAX_TOOL_LOOPS = 3
loops = 0

while True:
    response = await self.openai.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if loops == 0 else "none",
    )
    response_message = response.choices[0].message
    messages.append(response_message)

    if not getattr(response_message, 'tool_calls', None) or loops >= MAX_TOOL_LOOPS:
        break

    for tool_call in response_message.tool_calls:
        try:
            result = await self.call_mcp_tool(
                tool_call.function.name,
                args=json.loads(tool_call.function.arguments),
            )
        except Exception as e:
            logging.error(f"MCP tool error: {e}")
            result = "Error executing tool."
        messages.append({
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": tool_call.function.name,
            "content": result,
        })
    loops += 1
```

---

### 3. **Validación de entorno**

```python
def validate_env():
    required_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_CHAT_DEPLOYMENT"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

# Llama a validate_env() al inicio del main
if __name__ == "__main__":
    try:
        validate_env()
    except EnvironmentError as e:
        print(e)
        sys.exit(1)
    asyncio.run(main())
```


---

### 1. **Configuración básica de logging**

Coloca esto al inicio del archivo (después de los imports):

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("TaskPilotAgent")
```

---

### 2. **Uso de logging en el código**

Sustituye los `print` por llamadas a `logger.info`, `logger.error`, etc.

```python
# En vez de print(f"Prompt: {user_prompt}\\n")
logger.info(f"Prompt: {user_prompt}")

# Para tool calls
logger.info(f"Tool call requested: {tool_call.function.name} with args {tool_call.function.arguments}")

# Para errores
logger.error(f"OpenAI API error: {e}")
logger.error(f"MCP tool error: {e}")

# Para respuestas del modelo
logger.info("Model response received.")
```

---

### 3. **Ejemplo en el método chat**

```python
try:
    response = await self.openai.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    logger.info("OpenAI response received.")
except Exception as e:
    logger.error(f"OpenAI API error: {e}")
    return "Sorry, there was an error communicating with the language model."
```

---

¿Quieres que integre estos cambios directamente en tu archivo?