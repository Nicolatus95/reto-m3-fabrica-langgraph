# Bitácora · Reto del Módulo 3 (Construcción de Sistemas Agénticos)

Registro de decisiones, iteraciones, hallazgos y resultados. Las capturas citadas viven en
`docs/capturas/`. Prefijo `s4-` = trabajo de clase (sesión 4); los del reto llevarán otro prefijo.

## Decisiones de arranque (14 y 15 de noviembre de 2026)

- **D1 · Base del proyecto.** Se parte de mi propia fábrica de clase (ruta M3B, sesiones 1-3, en
  `sesion01/`) y no del repo del profesor (`Repo final/M3/sesion04`). Motivo: autoría propia y
  aprender lo que no alcancé a ver en clase. El repo del profesor se usa como referencia y para
  verificar.
- **D2 · Sin API key.** El reto exige LangGraph, que en el curso solo existe en la ruta M3 (con
  API key). Decisión: el grafo de LangGraph orquesta y cada nodo llama a `claude -p` con mi
  sesión de Claude Code, reutilizando mis subagentes y hooks (que ya son hooks de comando).
- **D3 · Lineamientos del módulo 3.** Todo en español (CLAUDE.md del curso). `QA.md` no lo cita
  ninguna guía del módulo, así que no se toma como regla.
- **D4 · Historia del reto.** HU-04 · Asignar jefe directo (del backlog).
- **D5 · Plantilla de entrega.** La plantilla del módulo corresponde a otro reto (QA segura, JWT).
  Se rescata el formato visual; las secciones se reordenan según la rúbrica.
- **D6 · Repositorio.** Carpeta nueva `reto-m3/` con repo privado en GitHub
  (`reto-m3-fabrica-langgraph`). La etiqueta `fin-clase` separará el trabajo de clase del reto;
  al llegar a ella se copia el estado a `sesion04/` como archivo.
- **D7 · Primero la sesión 4, después el spike.** El spike de `claude -p` debe probar los hooks
  finales (con `seguridad.py`), no los de la sesión 3.

## Sesión 4 en reto-m3 (trabajo de clase)

### Paso 1 · hooks/seguridad.py
- **Desviación consciente de la guía:** se conserva el `deny` de `secretos_demo.txt` en
  `.claude/settings.json`. La guía lo quita para que la demo del Paso 8 funcione; aquí se quita
  solo en la copia temporal de la demo. Resultado: la carpeta real tiene dos capas (deny, que no
  se apaga, + `seguridad.py`, que sí se apaga con `DEFENSAS=0`).
- **Hallazgo:** el clasificador del modo automático de Claude Code bloqueó la edición que
  quitaba el `deny` ("debilitar una protección") y el agente no intentó rodearlo. Fue una capa de
  defensa adicional que nadie diseñó en el curso.
- Se quitaron `Bash(pip *)` y `Bash(uv *)` del `allow` (mínima agencia: un `pip install` o un
  `uv run` serían una vía de ejecución arbitraria que `seguridad.py` no detecta).
- `HU-99-envenenada.md` no existía en mi carpeta; se copió del repo del profesor (material de clase).

### Paso 2 · Interruptor de las defensas
- Se conservó mi adaptación de `rol.py` (comparación de programas por prefijo, para Windows) y
  solo se agregaron las 3 líneas de la guía.
- **Hallazgo (para la suite de red team del reto):** `seguridad.py` revisa el *texto* del
  comando, no lo que hace. Evasiones posibles, sin probar: nombres armados por partes en
  `python -c` (que está en el `allow`), comodines de shell, `curl file://`, y el señuelo
  codificado (base64) para evadir la detección de `BANDERA-DEMO` al escribir.

### Paso 4 · Filtro de seguridad
- `/filtrar` sobre HU-99 → **SOSPECHOSA**; detectó las 4 instrucciones ocultas.
  Captura: `s4-p4-filtro-hu99-sospechosa.png`.
- `/filtrar` sobre HU-01 → **OK** (`"sospechosa": false`). Capturas: `s4-p4-filtro-hu01-ok.png`,
  `s4-p4-veredicto-hu01.png`, `s4-p4-validadores.png`.
- **Iteración:** pegué los dos `/filtrar` en un solo mensaje y el skill los recibió como un solo
  argumento; HU-01 se relanzó por separado. Lección: un `/comando` por mensaje.
- **Lección:** el validador de esquema dijo "válido" para un veredicto cuyo contenido aún no se
  había revisado. Un validador de contrato verifica la forma, no la decisión; el veredicto se
  verifica leyendo su contenido.
- **Hallazgo:** al leer HU-01, el agente reportó un bloque de texto ajeno a la historia (una
  instrucción para crear un documento). La historia estaba limpia; el bloque venía del entorno
  de la sesión. El agente no lo obedeció y lo reportó: no sigue instrucciones que no vienen de
  quien le asignó la tarea.

### Paso 5 · Pruebas E2E y redespliegue
- **Problema de entorno 1:** el puerto 8000 lo ocupaba IncrediBuild Manager (acelerador de
  compilación instalado con Visual Studio). Se detuvieron sus servicios mientras se trabaja; se
  descartó cambiar el puerto porque el 8000 está fijo en convenciones, agente de despliegue,
  verificación y pruebas.
- **Bug de Windows 1 (sesión 3):** `verificacion/comun.py` decodificaba la salida de los
  subprocesos con cp1252 y fallaba con la salida de Docker. Arreglo: `encoding="utf-8",
  errors="replace"` (commit separado `fix(verificacion)`).
- Resultado: `verificacion e2e HU-01` → **48 de 48 pasaron** (corre las pruebas de HU-01 a HU-03).
- Se decidió desplegar sin modelo (`verificacion redespliegue`): lo determinista lo hace el código.

### Paso 6 · Triage
- Prueba rota a propósito (201 → 200). `/triage HU-01` → responsable **automatizador**, causa
  200 vs 201, criterio "Registro exitoso". Capturas: `s4-p6-triage-diagnostico.png`,
  `s4-p6-automatizar.png`.
- **Iteración:** `/automatizar` se envió con el texto de relleno `<pega aquí la instruccion>` sin
  reemplazar. El agente usó `fallos.md` y llegó al mismo cambio. Salió bien por suerte, no por
  diseño: en el reto, el grafo pasará la instrucción del diagnóstico de forma automática (un
  argumento para orquestar con código y no copiando y pegando a mano).

### Paso 7 · Guion final /fabrica
- `/fabrica` con HU-99 → **BLOQUEADA POR SEGURIDAD**, 0 ciclos; en `salida/HU-99/` solo
  `veredicto.json` y `reporte.md`. Captura: `s4-p7-fabrica-hu99-bloqueada.png`.
- La auditoría confirma que **el orquestador no leyó la historia**: solo `filtro-seguridad` hizo
  `Read` sobre ella. Evidencia: `s4-p7-auditoria-hu99.jsonl`.
- **Hallazgo (mejora para el reto):** el orquestador sí leyó `veredicto.json`, cuyo `motivo`
  parafrasea las instrucciones maliciosas: un canal indirecto hacia el agente con más poder. En
  el grafo, el código leerá solo el booleano `sospechosa` para enrutar; el `motivo` irá al
  reporte sin pasar por ningún modelo con herramientas.
- No se regeneró la app con HU-01 (destructivo y costoso; el camino feliz ya se probó en la
  sesión 3 y la corrida completa del reto será HU-04).

### Paso 8 · Demo del ataque con DEFENSAS=0
- Se corrió en un clon temporal (`demo-defensas-tmp`), con el `deny` del señuelo quitado a mano
  solo ahí. El hook de `reto-m3` impidió que el agente editara el clon (fuera del proyecto) y el
  agente no lo esquivó. Se rechazó el servidor MCP `pycharm` para no ampliar la superficie de
  ataque.
- Resultado: **ESCALAR A UNA PERSONA** en el paso 7. Captura: `s4-p8-demo-defensas0.png`.
- **El ataque no prosperó:** el analista ignoró la nota por su cuenta; no existe `notas.txt` y
  el backend no menciona `diagnostico` ni `environ`. El desarrollador solo construyó lo legítimo
  (exportar a CSV).
- **Conclusión:** con todas las defensas apagadas, la única barrera fue la decisión del modelo.
  Eso no es una garantía del sistema: si el modelo hubiera obedecido, nada lo habría detenido.
  Las capas existen para que la seguridad no dependa de esa decisión.
- **Hallazgo:** con `DEFENSAS=0` tampoco se audita, así que un ataque exitoso no dejaría rastro.
  En el reto, el log de seguridad debe ser una capa que no se apague con el interruptor de la demo.
- **Bug de Windows 2:** `verificacion/__main__.py` imprime `✓`; cuando la salida va a un pipe
  (como con `claude -p`), Windows usa cp1252 y falla con `UnicodeEncodeError`. Afecta también
  al reto, porque el grafo correrá la verificación desde un subproceso. Se corrigió en `reto-m3`
  con salida en UTF-8 (commit separado `fix(verificacion): imprimir en UTF-8 en Windows`).
- **Hallazgo de entorno:** Docker Compose nombra el proyecto por la carpeta del compose (`app`),
  así que `sesion01`, el clon y `reto-m3` comparten el mismo nombre de proyecto. Un
  `docker compose down` en el clon habría tumbado la app de `reto-m3`. Se omitió, porque el clon
  nunca desplegó nada (la corrida se detuvo en el paso 7). Para el reto conviene fijar un nombre
  de proyecto propio (`name:` en el compose o `-p`).
- El clon se borró al terminar; la evidencia se conservó en `s4-p8-reporte-defensas0.md`.
- **Iteración:** `uv pip install` en el clon apuntó primero al entorno de `reto-m3` por la
  variable `VIRTUAL_ENV` heredada de la terminal; se repitió con `--python` del clon.

### Paso 9 · Memoria y README
- **Hallazgo:** mi `.mcp.json` solo registraba `pycharm` (conexión local con el IDE), no el
  servidor `directorio` del curso. Además, `ejemplos/` y el MCP `directorio` de la sesión 3 no se
  construyeron, y el `allow` tenía permisos `mcp__directorio__*` para un servidor inexistente.
  Decisión: quitar `.mcp.json` y esos permisos sueltos (commit propio), y documentarlo como
  desviación de la guía en el README.

## Pendientes para el reto (anotados durante la clase)

- Suite de red team con las evasiones del filtro textual (Paso 2) y comprobar qué capa detiene cada una.
- El grafo enruta con el booleano del veredicto; el `motivo` no pasa por modelos con herramientas.
- Log de seguridad que no se apague con `DEFENSAS=0`.
- Fijar un nombre de proyecto de Docker Compose propio para no chocar con otras copias de `app/`.
