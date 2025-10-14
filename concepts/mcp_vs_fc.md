

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