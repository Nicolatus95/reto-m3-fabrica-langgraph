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

### Comparación con la versión del profesor (`Repo final/M3B/sesion04`)
- Reporte completo: `docs/comparacion-profesor.md`. 73 archivos: 9 idénticos, 18 solo con
  diferencias de plataforma (CRLF, `.venv/Scripts` contra `.venv/bin`), 29 desviaciones ya
  documentadas y 16 con otras diferencias.
- Diferencias que se corrigieron:
  - `requirements.txt` de la raíz no incluía las dependencias del backend (en un entorno limpio,
    la verificación de la app fallaría). Se incluye `app/backend/requirements.txt` desde la raíz.
  - `*.jsonl` en `.gitignore` también ignoraba la evidencia de auditoría en `docs/capturas/`; se
    agregó una excepción.
  - `roles.py` le daba `uv` al automatizador (el profesor no lo hace). Se quitó, por coherencia
    con haber quitado `pip`/`uv` del `allow`.
- Diferencias que se conservan, documentadas como mejoras propias de clase: reglas extra en
  `analista.md` (no usar `Antecedentes:`) y `arquitecto.md` (inventariar `app/` antes de planear),
  `verificacion/__init__.py` distingue una dependencia faltante de una verificación inexistente,
  y `comun.py` resuelve `npm` con `shutil.which` en Windows.
- El resto son diferencias cosméticas (líneas en blanco, formato del JSON, saltos de línea).

### Cierre de la clase
- Commits de alineación y de `docs/`, etiqueta anotada `fin-clase` y push a GitHub. Todo lo
  anterior a `fin-clase` es trabajo de clase; lo posterior es el reto.
- Copia de archivo en `sesion04/` (sin `.git`, entornos, dependencias, datos locales ni
  `.mcp.json`). `sesion01/` no se tocó.

# Reto

## Fase 0 · Spike de `claude -p` desde Python
- La demo del Paso 7 ya probó que `claude -p "/fabrica ..."` ejecuta skills y subagentes con los
  hooks activos. El spike se reduce a lo que necesita el grafo: llamar a un skill desde Python y
  que el código lea el booleano del veredicto, salida estructurada sin herramientas (para el
  revisor), que las variables de entorno lleguen a los hooks, y cómo se ve un error.
- **Decisión de diseño:** cada nodo del grafo invoca uno de los skills existentes (`/filtrar`,
  `/criterios`, `/casos`, `/plan`, `/construir`, `/desplegar`, `/automatizar`, `/triage`); el
  código de Python verifica y decide la siguiente arista.
- **Resultados** (commit `4584786`, costo total 0.15 USD):
  - (a) `/filtrar` desde Python: el código leyó `sospechosa = False` del veredicto (6 s, 0.001 USD).
  - (b) Salida estructurada con Haiku y sin herramientas (`--json-schema` de un modelo Pydantic
    `Revision`): `aprobado = False` y la observación del `except:` vacío. Valida el enfoque del revisor.
  - (c) `DEFENSAS` pasado por el entorno llega a los hooks (DESACTIVADAS / ACTIVADAS según el caso).
  - (d) **Hallazgo:** un skill inexistente NO se detecta como error: `is_error = False`, código de
    salida 0 y una respuesta en lenguaje natural. Ni el código de salida ni el texto sirven para
    saber si un nodo hizo su trabajo. **Decisión:** el grafo juzga cada nodo por su artefacto
    (existe, cambió su fecha de modificación y valida contra su contrato); `is_error` solo detecta
    fallos de infraestructura.
- **Hallazgos técnicos:** el prompt va después de `--`, porque `--tools` acepta varios valores y se
  "tragaba" el prompt. Las llamadas sin `--model` usan el modelo de la sesión y cuestan unas 50 veces
  más que con Haiku: cada nodo debe fijar su modelo.

## Fase 1 · El orquestador en LangGraph (`flujos/fabrica.py`)
- **Decisiones previas:** `/construir` acepta correcciones, igual que `/plan`, `/desplegar` y
  `/automatizar` (commit propio; su ruta ya no depende del texto extra). El revisor va **al final**,
  después de E2E, porque el reto exige el orden spec → plan → código → tests → revisión de
  resultados. Hay una tabla `MODELOS` con el modelo de cada nodo (Haiku para el filtro y Sonnet para
  el resto).
- **Diseño:** 17 nodos. `Estado` con reducers (costo, bitácora, eventos de seguridad), aristas fijas
  y condicionales, fan-out y fan-in (despliegue ∥ automatizador), `Command(goto=...)` en el triage
  (supervisor), dos `interrupt()` (preguntas abiertas y aprobación del plan), `SqliteSaver` con
  `thread_id` por corrida y reanudación, y el diagrama exportado a `docs/grafo.mmd`.
- **Inyección de dependencias:** el grafo recibe `Servicios` (`ejecutar`, `verificar`, `salida`,
  `revisor`). En el modo ensayo (`--ensayo --escenario <preset>`) son dobles deterministas que
  escriben en una carpeta temporal: se prueban todas las rutas sin modelo, sin Docker y sin costo.
- **Resultado:** 16 pruebas en verde (10 rutas, 2 de reglas de seguridad y artefacto, 2 de revisión,
  diagrama y CLI) y `ruff` limpio. El flujo real con `claude -p` aún no se ha ejecutado.
- **Revisión externa del código (en el chat de planeación, sin el sesgo del autor).** Encontré tres
  huecos:
  1. `construir` se juzga solo con la verificación de la app, pero la app ya existe y verifica (HU-01
     a HU-03). Un `/construir` que no haga nada pasaría. Esto rompe la regla "cada nodo se juzga por
     su artefacto": hay que comprobar que `app/` cambió.
  2. `corregir_codigo` redespliega sin verificar antes la app, y no actúa si el redespliegue falla.
  3. El `motivo` del veredicto se escribe en `salida/seguridad.jsonl` y en `reporte.md`, ambos dentro
     de `salida/`, que los agentes pueden leer (`salida/*`). En una corrida posterior, el arquitecto,
     el desarrollador o el triage podrían leer la paráfrasis del ataque. Hay que mover el registro
     fuera del alcance de lectura de los agentes, y que el reporte no copie el `motivo`.

## Fase 1.1 · Correcciones de la revisión externa
- Hueco 1: `construir` exige que `app/` haya cambiado (huella de fechas de modificación de
  `app/backend` y `app/frontend/src`). Si no cambió, cuenta como intento fallido (commit `29a67fc`).
- Hueco 2: `corregir_codigo` verifica la app y después el redespliegue. Si alguno falla, escala con
  el log en vez de seguir a E2E a ciegas (`495c7c9`).
- Hueco 3: el `motivo` del veredicto vive solo en `registros/`, que está fuera de `salida/` e
  ignorada por git. El estado, el checkpoint y el reporte solo llevan el evento y sus booleanos
  (`1a73cb6`). Los veredictos de clase que tenían el `motivo` salieron de `salida/` (`c995054`).
  `CLAUDE.md` ganó la sección "Reto" (`fdd1bd4`).
- Resultado: 20 pruebas en `tests/`.
- **Lección:** "juzgar por el artefacto" exige que el artefacto sea algo que el nodo produce en esta
  corrida. Una verificación que ya pasaba antes del nodo no prueba que el nodo hizo su trabajo.

## Fase 2 · Planeación y revisión previa (chat de planeación)
- Estado real (15 de noviembre, 16:15): árbol limpio y `main` = `origin/main` = `c995054` según la
  referencia local. Desde el chat no se pudo consultar GitHub (no hay credenciales).
- **Hallazgo:** `registros/` solo está protegido de forma implícita. Ningún rol de `roles.py` la
  incluye en `lee`, pero `rol.py` no restringe al agente principal y `seguridad.py` no la menciona:
  el agente principal de un `claude -p` podría leer `registros/seguridad.jsonl`. Además,
  `auditoria.jsonl` (las entradas de cada herramienta, que en un ataque pueden traer la carga) vive
  en la raíz, al alcance de todos. Se corrige en la fase 2 (bloque B).
- **Diseño del revisor:**
  - Revisa solo lo que cambió en la corrida, y eso lo decide el código con git, no un agente.
  - Primero va la capa estática (`ruff`, `bandit`); si encuentra algo, rechaza sin llamar al modelo.
  - Después, un LLM sin herramientas, con salida estructurada y el código entre delimitadores
    aleatorios.
  - Sus observaciones están acotadas por el esquema, porque son un canal del revisor hacia el
    desarrollador, que sí tiene herramientas.
  - El código anula una aprobación que traiga observaciones de seguridad.
- **Registro de auditoría:** se escribe siempre, antes del interruptor `DEFENSAS`, en una ruta fija.
  Una ruta configurable por variable de entorno sería en sí misma una forma de evadirlo.
- **Lección:** una lista de permitidos protege lo que no menciona solo para quien está sujeto a la
  lista. Lo que deba ser inaccesible para todos se bloquea de forma explícita, en la capa que aplica
  a todos.
- **Línea base de la capa estática** (antes de la fase 2, sobre `app/backend`, que tiene el código
  de HU-01 a HU-03):
  - `bandit -ll` (Windows): **0 hallazgos** en 306 líneas. Captura: `r2-linea-base-bandit.png`.
  - `ruff` (Windows, `.venv`): **14 hallazgos**, confirmado. Captura: `r2-linea-base-ruff.png`.
    Corrido también desde el chat (ruff 0.17.5): 23 hallazgos. 9 son `EXE002`, un artefacto de los
    permisos de archivo de la carpeta montada que no aparece en Windows. Los 14 reales son 6
    `I001` (imports desordenados), 5 `B008` (los `Depends` de FastAPI, que es el patrón idiomático:
    un falso positivo), 2 `F401` (imports sin usar en `esquemas.py` y `servicio_empleados.py`) y 1
    `UP017`.
  - **Hallazgo:** no hay configuración de ruff en el repo y `requirements.txt` no fija versiones.
    Las reglas por defecto cambian entre versiones de ruff, así que la misma compuerta podría
    aprobar en una máquina y rechazar en otra. **Decisión:** fijar las versiones de ruff y bandit y
    declarar las reglas en una configuración del repo, con `B008` exceptuado para `Depends` y
    `Query`.
  - **Decisión:** HU-04 casi seguro tocará `routers/empleados.py`, que ya tiene hallazgos. Como no
    se edita `app/` a mano, la compuerta compara antes contra después y solo cuentan los
    hallazgos nuevos.
  - **Iteración:** el primer `ruff --statistics` falló porque el comando quedó pegado dos veces en
    la misma línea. Lección: un comando por línea al pegar en PowerShell.
- **Plan de la constructora (fase 2), revisado en el chat.** Aportes suyos que se aceptan:
  - El prompt viajaba como argumento y Windows limita la línea de comandos a ~32 KB, así que un
    diff de 60 KB no cabría. Ahora, por encima de ~20 000 caracteres, el prompt se envía por stdin.
  - Ruff 0.17.5 trae por defecto ~400 reglas, así que `ruff.toml` declara un conjunto explícito.
  - Versiones fijadas: ruff 0.17.5 y bandit 1.9.4.
  - Si la auditoría no puede escribirse con las defensas activas, el hook bloquea (exit 2): un
    error normal (exit 1) dejaría pasar la herramienta.
  - `aprobado=False` sin observaciones se trata como ESCALAR.
- **Ajustes pedidos en la revisión:**
  1. La base del diff es HEAD y el plan solo *documentaba* que `app/` debía estar limpio. Ahora el
     grafo lo comprueba al arrancar y guarda el commit base en el estado: una precondición que se
     verifica, no una nota.
  2. No todo hallazgo estático bloquea. El desarrollador no puede correr ruff (no está en sus
     `programas`), y un `I001` (orden de imports) gastaría el único ciclo de revisión en una
     corrección completa. Bloquean `F`, `E9`, `B` y bandit; `I`, `UP`, `E4`, `E7` y `RUF100`
     quedan como observaciones informativas.
  3. Bloquear cualquier comando que contenga la palabra "registros" daría falsos positivos en un
     dominio en español. Se bloquea por segmento de ruta, con pruebas de comandos legítimos que
     deben pasar.
  4. El `auditoria.jsonl` viejo de la raíz (46 KB, con entradas de la clase y de HU-99) seguía al
     alcance de los agentes. Se mueve a `registros/` en vez de borrarse.
  - Riesgo aceptado y documentado: la capa estática no analiza el front-end (JSX); ahí solo
    revisa el LLM.
- **Lección:** una limitación que se documenta pero no se verifica en el código es una regla que
  depende de que alguien la recuerde. Si se puede comprobar, el código la comprueba.
- **Orden dentro del bloque B:** los hooks del proyecto también protegen a la constructora. En cuanto
  `seguridad.py` bloquea `registros/`, ningún Bash de Claude Code puede moverse a esa carpeta, así
  que el `mv` del `auditoria.jsonl` viejo va antes de editar el hook. Desde ese momento, `registros/`
  solo se inspecciona desde la terminal de Nicolas.
- **Pendiente de decisión (HU-04):** propuesta de prohibir ciclos en la línea de reporte y de que,
  al dar de baja a un jefe, sus subordinados queden sin jefe.

## Fase 2 · Bloque A · Revisor real (commit `4fa19ff`)
- `flujos/revisor.py` (nuevo): qué se revisa lo decide git, desde el commit base de la corrida. La
  capa estática compara antes contra después, por archivo y regla. Bloquean los hallazgos nuevos de
  `F`, `E9`, `B` y bandit; los de `I`, `UP`, `E4`, `E7` y `RUF100` son informativos. Después va la
  capa LLM sin herramientas, con `Revision` y un marcador aleatorio por llamada. El código anula
  una aprobación que traiga observaciones de seguridad, y una salida ausente o inválida escala.
- `fabrica.py`: el stub `revisor_pendiente` se eliminó. `main()` no arranca una corrida real si
  `app/` tiene cambios sin commitear, y guarda `Estado["base"]`. `corregir_codigo` exige que `app/`
  cambie. `revision.json` y el evento `revision` van a `registros/`.
- `claude.ejecutar` manda por stdin los prompts de más de 20 000 caracteres; por ahora está probado
  solo con un doble.
- Ruff 0.17.5 y bandit 1.9.4 quedaron fijados. `ruff.toml` declara las reglas, con
  `line-length = 120` para respetar el estilo del repo.
- La configuración explícita destapó hallazgos en el código propio: un `zip` sin `strict`, dos
  variables `l` y el orden de imports en `compuerta.py` (sin tocar su lógica).
- Resultado: **58 pruebas** en verde (eran 20; tardan ~44 s porque corren ruff y bandit de
  verdad) y ruff limpio. En el ensayo, `revisor_rechaza` y `revisor_estatico_rechaza` terminan
  LISTA tras un ciclo de corrección, y `revisor_salida_invalida` termina en ESCALAR.
- **Revisión externa del chat. Hallazgo:** la capa estática se puede silenciar desde el mismo
  código que revisa. Bandit respeta `# nosec` y ruff respeta `# noqa`, así que un desarrollador
  manipulado por la historia podría escribir `eval(x)  # nosec` y la capa no lo vería. Se corrige
  con `--ignore-nosec` en bandit y `--disable-noqa` en ruff, en las dos corridas (antes y
  después) para que la comparación siga siendo justa. Va en un commit aparte, antes del bloque B.
- **Lección:** una compuerta que el código revisado puede apagar desde dentro no es una
  compuerta. Las supresiones (`noqa`, `nosec`, `type: ignore`) son instrucciones que trae el
  código, y el código bajo revisión no da instrucciones.
- Riesgo residual aceptado: el `detalle` de las observaciones del LLM es texto libre de un modelo
  que leyó código influido por la historia, y llega a un agente con herramientas. Lo acotan el
  esquema (máx. 5 observaciones, 300 caracteres, una línea) y la sustitución de rutas desconocidas.

## Fase 2 · Arreglo `noqa`/`nosec` (`44c1fd5`) y Bloque B (`0e682fc`)
- Arreglo: bandit corre con `--ignore-nosec` y ruff con `--ignore-noqa`, en la corrida base y en
  la actual. El flag que pidió el chat, `--disable-noqa`, no existe en ruff 0.17.5; la constructora
  usó el equivalente. Se agregaron tres pruebas: `# nosec` sobre `eval`, `# noqa: F401` nuevo, y un
  `noqa` heredado que no cuenta como hallazgo nuevo.
- Bloque B:
  - `registros/` queda bloqueada en `seguridad.py` para todos, incluido el agente principal:
    Read/Glob/Grep por ruta resuelta y Bash cuando nombra la carpeta como segmento de ruta.
  - La auditoría se escribe siempre, antes de mirar `DEFENSAS`, con el campo `defensas`. Si no se
    puede escribir con las defensas activas, el hook falla cerrado (exit 2).
  - El `mv` del log viejo a `registros/auditoria-clase.jsonl` se hizo antes de activar el bloqueo.
  - Resultado: 106 pruebas en verde y ruff limpio.
- Verificado desde el chat: existe `registros/auditoria-clase.jsonl` (74 KB), ya no hay
  `auditoria.jsonl` en la raíz, y `registros/auditoria.jsonl` recibe líneas con
  `"defensas": "activas"` (las de la propia constructora, agente principal).
- **El hook frenó dos veces a su propia autora:**
  1. Bloqueó la escritura del hook y de su prueba porque contenían el marcador del señuelo. La
     constructora no lo esquivó: partió la constante en dos cadenas, lo que es equivalente.
  2. Bloqueó un `sed` porque el texto `env=env` coincidió con la regla de variables de entorno.
     Es un falso positivo del filtro textual, y es evidencia para el red team: el filtro juzga el
     texto, no la intención (bloquea lo inocente que se le parece y deja pasar lo malicioso que no
     se le parece).
- **Revisión externa del chat. Hallazgo:** el bloque B impide *leer* `registros/`, pero no
  *escribir* en ella. Un `Write` sobre `registros/auditoria.jsonl` reemplazaría el archivo completo
  y borraría el rastro, y un `Edit` lo alteraría. Proteger la confidencialidad del registro no
  protege su integridad. Además, `NotebookEdit` no está en el matcher de `seguridad.py`: no se
  audita ni se revisa su contenido. Se corrige en un commit aparte antes del bloque C.
- **Lección:** un registro de seguridad necesita dos protecciones distintas: que no se pueda leer
  (confidencialidad: no filtra la carga del ataque) y que no se pueda modificar (integridad: el
  rastro sobrevive al ataque). La segunda es la que hace útil un log después de un incidente.
- Pendiente para la documentación: el README todavía menciona `auditoria.jsonl` en la raíz (5
  líneas). Se actualiza en la fase de documentación, no ahora.

## Fase 2 · Integridad del registro (`d16bde3`), Bloque C (`a94e08b`) y spike (`ecc066b`)
- `seguridad.py` también bloquea Write, Edit, MultiEdit y NotebookEdit cuyo destino resuelto cae
  en `registros/`. `NotebookEdit` entró al matcher de `.claude/settings.json`: ahora se audita y su
  `new_source` se revisa contra el señuelo. Hay además una prueba que lee el `settings.json` real,
  para que el matcher no se pierda en silencio.
- HU-04 creada (`historias/HU-04-asignar-jefe-directo.md`) y reglas 8 a 12 en
  `contexto/reglas_negocio.md`, con la fila `jefe_id`.
- `spikes/probar_revisor.py`: un repo git temporal con `eval(x)  # nosec` y un comentario que le
  ordena al revisor aprobar. El paso 1 es sin modelo (la capa estática rechaza, 0 llamadas); el
  paso 2 es una llamada real solo a la capa LLM; con `--largo` agrega ~30 KB para pasar por stdin.
- Resultado: 120 pruebas en verde y ruff limpio. Revisión externa del chat: sin hallazgos.

- **Spike del revisor, corrido con permiso** (`python -m spikes.probar_revisor --largo`). Captura:
  `r2-spike-revisor.png`.
  - Paso 1 (sin modelo): **rechazada con 0 llamadas al modelo**, por bandit B307 sobre el `eval`.
    El `# nosec` no lo ocultó: el arreglo `44c1fd5` funciona.
  - Paso 2 (llamada real a Sonnet, sin herramientas, ~30 KB por stdin): **rechazada**, con 0.32 USD
    y cuatro observaciones. Tres son de seguridad: la orden escrita en el comentario identificada
    como inyección de prompt y no obedecida, el `eval` como ejecución de código arbitrario, y el
    `# nosec` como intento de silenciar la capa estática. La cuarta es de corrección: las 1500
    funciones de relleno no implementan HU-04.
  - Queda probado con una llamada real el envío por stdin de los prompts largos, que hasta ahora
    solo se había probado con un doble.
  - **Conclusión:** las dos capas detectaron el ataque por caminos independientes: la estática por
    reglas, sin modelo, y la LLM por comprensión. Con cualquiera de las dos bastaba para rechazar.
    Eso es defensa en profundidad: ninguna capa es la única barrera.
  - **Observación de costo:** una revisión de ~30 KB costó 0.32 USD con Sonnet. El diff de HU-04
    será mucho menor, pero el revisor es de los nodos más caros por llamada.
- **Fase 2 cerrada.** Commits `4fa19ff`, `44c1fd5`, `0e682fc`, `d16bde3`, `a94e08b` y `ecc066b`;
  120 pruebas en verde.

## Nota para la entrega · Agentes del reto contra la clase
- Desde `fin-clase` no se agregó ningún subagente a `.claude/agents/` (siguen los 8 de la clase);
  el único cambio ahí fue que `/construir` acepta correcciones. El agente nuevo del reto es el
  **revisor** (`flujos/revisor.py`): una llamada al LLM **sin herramientas** y con salida
  estructurada, y no un subagente. Se decidió así por mínima agencia: un agente que lee código
  posiblemente manipulado no necesita herramientas para opinar sobre él.
- El orquestador también cambió de naturaleza: en clase era el agente principal siguiendo el
  guion `/fabrica`; en el reto es código (LangGraph). El triage hace de supervisor con
  `Command(goto=...)`.
- Correspondencia con los 4 roles que pide el reto: planificador = analista + arquitecto,
  implementador = desarrollador, tester = diseñador de pruebas + automatizador, reviewer =
  revisor. Total: 9 agentes con rol propio (rúbrica: "5+ agentes con roles bien definidos").

- **Hallazgo (revisión contra el plan del reto):** el reto pide que el flujo entregue "código +
  pruebas + documentación". Hoy el grafo produce código, pruebas y `reporte.md`, pero ningún nodo
  genera documentación de la historia. Es el único hueco que justificaría un agente más
  (documentador). **Decisión:** se agrega antes de la corrida real, porque la corrida es la
  evidencia principal. Nodo `documentar` (Haiku, sin herramientas) entre `revisar` y `reporte`. El
  código decide qué recibe, el modelo devuelve un contrato `Documentacion`, el código verifica que
  cada endpoint aparezca en el diff y cada regla exista, y Python escribe el markdown. Así, la
  documentación que afirma algo queda respaldada por el código.

- **Revisión del plan del nodo `documentar`.** Aceptado: reutiliza el revisor (los mismos
  delimitadores, el mismo diff y el mismo límite), con saneado de markdown, HTML y enlaces, texto de
  las reglas tomado del archivo y no del modelo, y la aclaración de qué partes verifica el código.
  **Hallazgo:** la "limitación aceptada" de las rutas no es un caso raro, es el caso normal en
  esta app. El prefijo `/api` está en `main.py` y `/empleados` en el router, así que una ruta
  correcta como `/api/empleados/{id}/jefe` nunca aparece literal en el diff de HU-04, y la
  evidencia principal saldría marcada «(no verificado)». **Ajuste:** verificar contra el OpenAPI de
  la app ya desplegada (`/openapi.json`; el nodo corre después de E2E), con método y ruta y los
  parámetros `{...}` normalizados. Si la app no responde, se usa el diff como respaldo.
- **Lección:** antes de aceptar una limitación, hay que comprobarla contra el caso real. Lo que en
  abstracto parecía un borde era, en esta app, la ruta de siempre. Además, la fuente de verdad de
  "qué endpoints existen" es la app en ejecución, no el texto del diff.

## Fase 2 · Renombre (`1152166`) y nodo `documentar` (`95e620b`)
- `1152166`: la categoría `correctitud` (un calco del inglés que no existe en español) pasa a
  `corrección`.
- `95e620b`: nodo `documentar` (Haiku, sin herramientas) entre `revisar` (aprobada) y `reporte`.
  - El código decide qué recibe el modelo: el diff desde la base, las reglas y los criterios, entre
    delimitadores aleatorios.
  - El modelo devuelve un contrato `Documentacion` (`extra="forbid"`); los textos se sanean y
    Python arma `salida/HU-xx/documentacion.md`.
  - Los endpoints se verifican contra el `/openapi.json` de la app desplegada, con los parámetros
    normalizados y con o sin `/api`. Si la app no responde, se verifican contra el diff y el
    documento lo dice.
  - Las reglas se verifican contra `reglas_negocio.md`, y su texto lo pone el código.
  - El reporte solo enlaza el documento si esta corrida lo escribió (`documentacion_ok`): así no
    enlaza un archivo viejo.
- Resultado: **153 pruebas** en verde y ruff limpio. En el ensayo, `lista` termina LISTA con
  documentación y `documentar_invalido` termina en ESCALAR. `docs/grafo.mmd` se regeneró
  (18 nodos).
- Límites aceptados: con el respaldo por diff no se verifica el método; la verificación por OpenAPI
  depende de que la app esté en `localhost:8000`, así que antes de la corrida hay que comprobar que
  no hay otra copia de `app` levantada; no hubo llamada real ni app real (solo dobles).
- Revisión externa del chat: sin hallazgos.
- **Lección:** «verificado» debe decir contra qué. El documento nombra su fuente de verificación y
  marca lo que no pudo verificar, en vez de descartarlo.

## Pendientes para el reto (anotados durante la clase)

- Suite de red team con las evasiones del filtro textual (Paso 2) y comprobar qué capa detiene cada una.
- El grafo enruta con el booleano del veredicto; el `motivo` no pasa por modelos con herramientas.
- Log de seguridad que no se apague con `DEFENSAS=0`.
- Fijar un nombre de proyecto de Docker Compose propio para no chocar con otras copias de `app/`.
