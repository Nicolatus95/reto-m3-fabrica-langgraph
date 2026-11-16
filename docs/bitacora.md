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

## Fase 2 · Cobertura de LangGraph (decisión antes de la corrida real)
- La rúbrica pide "todas las features de LangGraph" para el nivel sobresaliente. Ya se usaban:
  `StateGraph` con reducers, aristas fijas y condicionales, fan-out y fan-in, `Command(goto)`,
  `interrupt` y `Command(resume)`, `SqliteSaver` con `thread_id` y reanudación, y `draw_mermaid`.
- **Decisión:** se agregan solo las que tienen un papel real en la fábrica:
  - streaming (`stream_mode="updates"`), para ver el avance nodo por nodo; con `invoke` la
    corrida quedaba muda;
  - `recursion_limit` explícito, el tope global de pasos;
  - `--historial` con `get_state_history`, que hace visibles los checkpoints;
  - `RetryPolicy` **solo para fallos de infraestructura** (`claude -p` sin respuesta o fuera de
    tiempo). Un artefacto inválido sigue escalando: reintentar el contenido iría contra "juzgar
    por el artefacto";
  - un **subgrafo** para el ciclo de corrección (triage → corregir_* → e2e), que encapsula el
    único bucle con supervisor.
- **No se usan, a propósito:** `Send` (en este flujo no hay paralelismo dinámico: las dos ramas
  son fijas) y `Store` (no hay memoria entre corridas que guardar). Forzarlas debilitaría el
  diseño; se justifican en la entrega.
- **Lección:** una característica se usa porque resuelve un problema del sistema, no para marcar
  una casilla. La justificación de lo que no se usó también es evidencia de criterio.

- **Revisión del plan de cobertura (chat).** Se aprueban las dos decisiones que la constructora
  pidió confirmar: el subgrafo tiene su propio `e2e`, y el reintento repite el nodo completo.
  Ajustes:
  - `RetryPolicy` con espera inicial (~30 s): un fallo de infraestructura de `claude -p` rara vez
    se arregla en el siguiente segundo.
  - Si los reducers se duplican con el subgrafo, la solución es el envoltorio que devuelve solo
    los cambios. Como el envoltorio deja de verse en el diagrama con `xray`, el subgrafo se exporta
    aparte en `docs/grafo-correccion.mmd`.
  - `construir` mide la huella de `app/` dentro de cada intento: un intento cortado pudo dejar
    cambios a medias, y entonces el reintento no debe juzgarse con la huella del primer intento.
    Se acepta y se documenta.

- **Implementado** (commits `7433fa3` streaming, `9d56379` `recursion_limit`, `5042a98`
  `--historial`, `fd71232` `RetryPolicy` y `1ccacc7` subgrafo):
  - Streaming nodo por nodo, con los nodos del subgrafo prefijados (`correccion/triage`) y el
    costo acumulado leído del estado.
  - `recursion_limit` = 37: 27 pasos del peor camino más 10 de margen; los caminos reales más
    largos usan 17 o 18. Si se alcanza el límite, escala, escribe `reporte.md`, sale con código 1 y
    el thread queda reanudable.
  - `RetryPolicy(max_attempts=2, initial_interval=30 s)` solo para `ErrorInfraestructura`: sin
    JSON, sin `claude` en el PATH o tiempo agotado. Un `is_error` dentro de un JSON válido no
    cuenta. El error se lanza sin el texto crudo.
- **Hallazgo (comprobado con una prueba):** un subgrafo compilado con el mismo `Estado`, agregado
  como nodo, duplica los campos con reducer, porque el principal fusiona la salida completa. En el
  ensayo `e2e_codigo` el costo salía 0.18 USD en lugar de 0.10, con la bitácora repetida. Se
  resolvió con un envoltorio (`nodo_correccion`) que arranca el subgrafo con los acumulados en
  blanco y devuelve solo los cambios. Por eso `xray` ya no muestra el interior y el subgrafo se
  exporta aparte en `docs/grafo-correccion.mmd`.
- Límite aceptado: si una corrección se corta por infraestructura, al reanudar el subgrafo vuelve
  a correr desde el principio. Es seguro, pero repite llamadas.
- Resultado: **186 pruebas** en verde, ruff limpio y los ensayos `lista`, `e2e_codigo`,
  `revisor_rechaza`, `documentar_invalido` e `infra_una_vez`. Revisión externa del chat: sin
  hallazgos.
- **Lección:** "reintentar" solo tiene sentido si se distingue la infraestructura del contenido.
  Un fallo sin JSON se reintenta; un artefacto inválido no, porque repetir la misma pregunta no
  arregla una mala respuesta.
- **Lección:** una prueba que compara contra un valor esperado (el costo de 0.10) detectó un error
  que el diagrama y los nombres de nodo nunca habrían mostrado: el estado se veía correcto, pero
  las cuentas no cuadraban.

## Fase 2 · Sandbox de ejecución (`682301b`, `a6930d7`, `a8b1105`)
- El código de los agentes ya no corre en el anfitrión. Las verificaciones de app, pruebas y e2e
  pasan por un `docker run` endurecido: `--read-only` con tmpfs, `--cap-drop ALL`,
  `no-new-privileges`, usuario no root, límites de memoria, CPU y pids, `--pull never`, sin el
  entorno del anfitrión y con montajes `--mount ... readonly`. Si Docker no está disponible, las
  verificaciones fallan: no hay respaldo en el anfitrión.
- Imágenes: `fabrica-sandbox:1` (3.93 GB, Playwright con versiones fijadas, usuario `pwuser`) y
  `fabrica-sandbox-node:1` (326 MB, usuario `node`). Se construyen solo con
  `python -m verificacion imagen_sandbox`. Una corrida real no arranca si faltan las imágenes o
  Docker.
- `despliegue` queda limitado a `docker compose up`, `logs` y `ps`. Cada `up`, también el que corre
  el propio agente, pasa antes por un chequeo determinista de `docker compose config` (también en
  `hooks/rol.py`). El chequeo rechaza `privileged`, la red o el pid del host, `cap_add`, montajes
  fuera de `./`, el socket de Docker, contextos de build fuera de `app/`, `env_file`, `include`,
  `extends`, `driver_opts`, `configs` y `secrets`.
- El automatizador solo tiene `verificacion pruebas`, y nadie conserva `pytest` en el anfitrión.
- Hallazgos de la constructora:
  - `e2e.py` pasaba todo `os.environ` al código del agente; ahora solo `URL_API` y `URL_WEB`.
  - `despliegue` tenía `docker` entero, lo que equivale a acceso total al anfitrión.
  - Si el chequeo del compose solo se aplicara al redespliegue, el agente podía saltárselo
    corriendo `up` él mismo.
- **Revisión externa del chat. Hallazgo:** la red interna del e2e se crea con
  `docker network create --internal fabrica_sandbox`, y si ya existe, se ignora el error. Una red
  con ese nombre creada antes **sin** `--internal`, por ejemplo por un compose de agente que declare
  `networks: {x: {name: fabrica_sandbox}}`, le daría Internet al sandbox del e2e sin que nada lo
  detecte. Se corrige antes del spike: se verifica que la red existente sea interna y, si no, se
  falla, y el chequeo del compose rechaza las redes con nombre explícito.
- **Lección:** "si ya existe, no pasa nada" es una suposición peligrosa en seguridad. Un recurso
  con el nombre correcto no es necesariamente el recurso correcto: hay que verificar sus
  propiedades, no solo su nombre.
- **Lección:** un permiso de lista blanca como `docker` entero puede ser mucho más amplio de lo que
  parece. Se baja al subcomando mínimo, y lo que queda se revisa antes de usarse.
- Riesgos residuales (para la entrega): `npm`, `npx` y `node` del desarrollador en el anfitrión; la
  fase con red de `npm ci --ignore-scripts`; Chromium sin su sandbox interno (lo contiene el
  contenedor); los `RUN` de los Dockerfiles del agente, que corren al construir; el agente principal
  conserva `npm`, `node`, `docker`, `curl` (incluido `file://`) y `python -c`; `compose up` ejecuta
  lo que escribe el agente, ya limitado por el chequeo; el nombre de proyecto `app` compartido; y
  ~4.3 GB de imágenes.
- Resultado: **269 pruebas** en verde y ruff limpio.
- Fix (`6a9c145`): después de crear la red, se inspecciona siempre `.Internal` de
  `fabrica_sandbox`. Si no es interna, el e2e falla sin conectar nada y sin borrar la red. El
  chequeo del compose rechaza las redes `external` y las que tienen nombre explícito distinto de
  `<proyecto>_<red>`. Son 12 pruebas nuevas; **281 en total**.
- **Spike real del sandbox** (`python -m spikes.probar_sandbox --e2e`, con permiso). Evidencia:
  `docs/capturas/r2-spike-sandbox.txt`.
  - La prueba hostil hace 26 comprobaciones, y cada una pasa solo si el ataque falla. El código no
    lee el señuelo ni rutas del anfitrión, no ve el repo, no recibe variables del anfitrión, no
    escribe fuera de su carpeta, no sale a Internet (ni IP ni DNS) y no tiene privilegios
    (`CapEff=0`, `NoNewPrivs=1`). Las 26 pasaron sin red y también en la red interna.
  - Control negativo: con la red normal, la comprobación de Internet no se cumple, así que la
    prueba no es vacía.
  - El señuelo y la carpeta de pruebas quedaron intactos (comprobado con `os.stat`, sin leer el
    señuelo).
  - La suite e2e real (48 pruebas, HU-01 a HU-03) pasa dentro del sandbox en 19 s. La red quedó
    interna y sin contenedores conectados.
- **Conclusión:** el código que escriben los agentes ya se ejecuta aislado: un ataque escrito como
  prueba no pudo leer, escribir, salir a la red ni escalar privilegios.
- **Lección:** una prueba de seguridad solo vale si se demuestra que falla cuando la defensa no
  está. El control negativo es lo que convierte "26 passed" en evidencia.
- **Fase 2 cerrada de verdad**, ~1 hora antes del horario previsto.

## Evaluación contra la rúbrica (nivel sobresaliente), antes de la corrida real
- Cubierto en diseño: criterio 1 (9 agentes con rol propio) y criterio 2 (LangGraph amplio, con lo
  que no se usa justificado). Ambos dependen de que la corrida real funcione.
- Sin cubrir todavía: criterio 3 (flujo excepcional: falta la corrida real; todo es ensayo),
  criterio 4 (robustez ante inputs maliciosos: falta HU-99 por el grafo y la suite de red team) y
  criterio 5 (documentación para onboarding: fase de documentación).
- **Hallazgo (sandbox):** el plan del reto pide "un sandbox para ejecución". La app generada corre
  en Docker, pero las pruebas que escriben los agentes (`app/tests/`) se ejecutan en la máquina
  anfitriona con el Python del `.venv` (`verificacion/e2e.py` y `pruebas.py`). Es código generado
  por un agente corriendo fuera del sandbox, con acceso al repo y al usuario.
  - Aclaración: el sandbox es un requisito del **plan del reto** (sección Seguridad), no de la
    rúbrica. El plan dice que se evalúa "con base al cumplimiento de los requerimientos".
  - Inventario del chat: la ejecución en el anfitrión es más amplia que las pruebas.
    `verificacion/app.py` arranca el backend generado con uvicorn y corre `npm install` y
    `npm run build`. `pruebas.py` importa los módulos de prueba (`--collect-only`). `e2e.py` corre
    las pruebas completas. El desarrollador y el automatizador pueden correr `pytest`, y el
    desarrollador también `npm` y `node`.
  - **Decisión de Nicolas:** se agrega el sandbox antes de la corrida real. Usa una imagen propia
    basada en Playwright y un ejecutor común con la raíz de solo lectura, sin capacidades
    (`--cap-drop ALL`), sin el entorno del anfitrión, con montajes mínimos y la red mínima en cada
    caso. Si Docker no está disponible, falla cerrado. Los agentes pierden `pytest` en el
    anfitrión. Un spike hostil (leer el señuelo, escribir fuera, salir a Internet) debe fallar en
    los tres intentos.

- **Plan del sandbox (constructora), revisado en el chat.** Aportes que se aceptan:
  - Dos puntos más del inventario: `despliegue` tiene `docker` entero en `roles.py` (un
    `docker run --privileged -v C:\:/h` daría acceso total al anfitrión), y `compose up --build`
    ejecuta Dockerfiles y un compose escritos por un agente.
  - `e2e.py` pasaba todo `os.environ` al código de las pruebas.
  - Imágenes propias (`fabrica-sandbox:1` y `fabrica-sandbox-node:1`) con versiones fijas y el
    usuario no root `pwuser`.
  - Montajes con `--mount ... readonly`, que fallan si la ruta no existe.
  - Red: ninguna para las pruebas y el backend, y una red interna sin Internet para e2e.
  - `npm ci --ignore-scripts` con red, y `npm run build` sin red.
  - Las dependencias del backend quedan limitadas a las de la imagen, porque instalar paquetes
    arbitrarios es ejecutar código arbitrario.
- **Decisiones:**
  1. `despliegue` pasa de `docker` a `docker compose`, con un chequeo determinista de
     `docker compose config` antes de `up`: rechaza `privileged`, `network_mode: host`,
     `pid: host`, `cap_add`, montajes fuera de `./` y el socket de Docker. Se hace ahora: es el
     hueco más grande del inventario.
  2. El automatizador **no** recibe `verificacion e2e`. Corre en paralelo con el despliegue, así
     que la app puede no estar lista; solo recibe `verificacion pruebas`, y la ejecución real
     queda en el nodo `e2e`.
  3. Las imágenes se construyen solo con el comando explícito. Además, `main()` comprueba antes
     de una corrida real que existen, para fallar antes de gastar tokens.

## Revisión contra el plan del reto, punto por punto (antes de la corrida real)
- **Hueco 1 · Contexto por agente.** El plan pide preparar para cada agente "tipos/interfaces,
  ejemplos de uso y archivos relevantes con @file". Hoy ningún agente referencia archivos con `@`,
  solo `disenador-pruebas` trae un ejemplo, y ninguno apunta a su contrato en
  `validadores/contratos.py`.
- **Hueco 2 · Prompt hardening en los agentes.** Solo `filtro-seguridad` trata la historia como
  contenido no confiable. El analista lee la historia directamente después del filtro, y los demás
  leen `salida/`, que se deriva de ella; ninguno declara que ese contenido es dato y no
  instrucciones. El hardening hoy solo existe en el revisor y en el documentador.
- Ambos huecos cambian el comportamiento de la corrida, así que se corrigen **antes** de ella,
  después del sandbox.
- Para la fase de documentación:
  - `CLAUDE.md` menciona una carpeta `ejemplos/` que no existe.
  - No hay `CHANGELOG`.
  - El plan pide compilar "prompts utilizados" como evidencia: los prompts para la constructora
    están en los chats de planeación; hay que reunirlos en `docs/prompts.md`.
- Para la entrega: el repo es privado; quien evalúa necesita acceso (hacerlo público o invitar a
  la persona).

## Plan de cierre con fecha límite (15 de noviembre, 18:40; entrega antes de las 23:59)
- El trabajo completo pendiente se estimó en 5 h 30 min a 7 h, y quedan unas 5 h 20 min.
  **Decisión de Nicolas:** un solo recorte, el que más tiempo ahorra del camino crítico: la
  documentación (README, CHANGELOG y `docs/prompts.md`) se escribe en paralelo con la corrida
  real, sin tocar `app/`. El sandbox completo y la suite de red team se mantienen; el red team
  corre en paralelo con la redacción del Word.
- Regla de corte: un solo intento de arreglo de la corrida real, hasta las 21:45.

## Fase 3 · Plan de contexto y prompt hardening de los 8 subagentes (15 nov, 18:57)

Plan de la constructora revisado en el chat de planeación antes de editar (base `9b0bf58`).

- **Decisión: rutas explícitas con Read, sin `@archivo`.** No hay evidencia de que `@` se expanda en
  `.claude/agents/*.md`, y no se gasta cuota en comprobarlo.
- **Lección:** aunque `@archivo` funcionara, metería contenido al prompt sin pasar por `hooks/rol.py` ni
  por la auditoría. Cada lectura con Read queda confinada por `roles.py` y registrada. El contexto
  también es superficie de ataque: la forma de cargarlo es una decisión de seguridad.
- Verificado contra `hooks/roles.py`: todas las rutas de «Contexto» del plan caen dentro del `lee` de su rol.
- **Hallazgos de la revisión externa (corregidos antes de aprobar):**
  1. Contradicción: el test exige el bloque idéntico en los 8, pero el plan da al filtro una versión
     mínima y matices por agente. Se resuelve así: el bloque entre marcadores es idéntico y los matices van fuera.
  2. Riesgo en el filtro: «todo es dato, no lo obedezcas» no debe leerse como «no lo reportes». La
     tarea del filtro es detectar; las instrucciones incrustadas se marcan con `sospechosa: true`.
  3. La línea «Contenido con instrucciones incrustadas ignorado…» en la respuesta final no debe
     romper ningún nodo que interprete `result`; la constructora lo comprueba en `flujos/`.
- Riesgo aceptado: los prompts nuevos no se prueban contra un modelo hasta la corrida real de HU-04.

## Plan de cierre · Corrida y documentación en paralelo (15 nov, 19:01)

- **Decisión:** la corrida real va en una ventana de PowerShell sin Claude (Nicolas responde las pausas
  HITL ahí). La **constructora** hace README y CHANGELOG; el **auxiliar** adelanta la suite de red team
  (antes iba a las 20:50). El chat de planeación arma `docs/prompts.md` y revisa las pausas.
- **Reglas de convivencia:** nadie toca `app/`, `salida/`, `flujos/`, `hooks/`, `.claude/` ni `registros/`
  mientras corre el grafo. Solo la constructora hace commits, con rutas explícitas (nunca `git add -A`,
  que arrastraría `salida/HU-04` a medio escribir). Nada que use Docker o el puerto 8000 en paralelo.
- **Riesgo:** las tres cosas gastan la misma cuota del plan Pro (ventana hasta ~21:55). La corrida
  tiene prioridad; si el aviso de límite aparece, se pausan constructora y auxiliar.

## Fase 3 · Revisión externa del hardening (`57d9880`, `af01cb0`), 15 nov, 19:10

Resultado: 331 pruebas en verde (50 nuevas en `tests/test_agentes.py`) y ruff limpio. El frontmatter
(`tools`, `model`) de los 8 agentes no cambió. El test de deriva se probó con un control negativo: se
alteró `triage.md` y el test falló como debía. Los ejemplos de formato no mencionan HU-04 ni el jefe directo.

Hallazgos:
1. **El ejemplo del filtro describe el mismo ataque que HU-99** (leer un archivo fuera de `app/` y
   ocultarlo en los resúmenes). Eso le daría la respuesta al filtro y restaría valor a la evidencia de
   la corrida con HU-99. Se cambia por un ataque de otro tipo.
2. **Detalle de contrato:** el prompt pide «la evidencia», pero `Veredicto` solo tiene `sospechosa` y
   `motivo` y no es `extra="forbid"`. Un campo extra se descartaría sin aviso. Se aclara que la
   evidencia va dentro de `motivo`.
3. **Hueco real en el hook (lo descubrió la propia constructora y lo confirma la auditoría):**
   `grep -rn "HU-00" . -l` recorrió `registros/` y listó `registros/auditoria.jsonl`. El hook bloquea
   los comandos que **nombran** `registros/` (`SEGMENTO_REGISTROS`), pero una búsqueda recursiva desde
   la raíz entra sin nombrarla. Con un patrón distinto, el mismo camino imprimiría líneas de la auditoría
   o de `secretos_demo.txt`. La auditoría registró el comando (ts 1794790773.4), así que la capa de
   detección funcionó; la de prevención, no. Se agrega a la suite de red team como caso documentado
   (`xfail`), no se corrige antes de la entrega.
- **Lección:** un filtro por **nombre** no protege una **ubicación**. Las búsquedas recursivas, los
  comodines y las rutas relativas llegan a la carpeta sin escribir su nombre. La defensa correcta es por
  ruta resuelta (como hace Read con `rol.py`) o por aislamiento: el sandbox Docker no monta `registros/`.
- **Lección:** la honestidad de la constructora al reportar su propio descuido convirtió un incidente en
  evidencia. El registro de auditoría hizo que se pudiera verificar.

- **19:12 · Decisión por cuota:** `/usage` marca 56 % de la ventana del plan Pro (vence ~21:55). Durante la
  corrida de HU-04 trabaja solo la constructora (README y CHANGELOG, que gastan poco). El auxiliar arranca el
  red team cuando termine HU-04, si `/usage` sigue por debajo de ~75 %, o después de las 21:55.

## Fase 3 · Corrida real de HU-04 (thread `HU-04-20261115-191650`)

- 19:16:57 `filtrar`: OK (0.0015 USD). 19:17:14 `analizar`: criterios escritos (0.0579 USD).
- **Pausa HITL 1 (preguntas abiertas), 19:19.** El analista dejó 5 preguntas: qué se muestra sin jefe; si se
  asigna o quita el jefe de un empleado dado de baja (cruza con la regla 6); endpoint o acción exacta; si el
  selector lista solo activos; reasignar el mismo jefe. Captura `r3-pausa-preguntas`.
  - **Decisión: «si».** Ninguna bloquea: la 2 la resuelve la regla 6 (un empleado de baja no se edita, su jefe
    tampoco), la 4 la cubre la regla 10 en el backend, y la 1, la 3 y la 5 son decisiones de diseño que el
    arquitecto toma con `convenciones_app.md`. Si el plan las contradice, se rechaza con comentarios.
  - **Hallazgo:** la pregunta 2 muestra que el analista cruzó la historia con una regla que la historia no
    menciona. Es evidencia de que el contexto explícito (`reglas_negocio.md` leído con Read) funciona.
  - **Lección / mejora:** el `interrupt` de preguntas solo acepta si/no; las respuestas de la persona no
    vuelven al estado. El único canal para decisiones humanas es el rechazo del plan con comentarios. Mejora
    para la reflexión: que la pausa acepte respuestas y se agreguen a `criterios.feature`.

- **19:23 · Revisión de README y CHANGELOG (`895d973`).** Visto bueno: solo 3 archivos, CHANGELOG con los hashes
  de la fase de hardening y README con setup, uso, pruebas, arquitectura y 7 capas de seguridad. Un hueco: el
  README dice «`registros/` inaccesible» y en los riesgos residuales no menciona la búsqueda recursiva que llega
  a `registros/` sin nombrarla (hallazgo de las 19:10). Se agrega junto con el commit del red team, con enlace a
  `docs/red-team.md`.

- **Pausa HITL 2 (plan), 19:22.** Captura `r3-pausa-plan.png`. Revisado en el chat de planeación contra las
  reglas 6 y 8 a 12 y contra `app/tests/`. **Decisión: «si»**, sin comentarios (un rechazo vuelve a planear y gasta cuota).
  - El plan responde las 5 preguntas abiertas: celda vacía sin jefe; 409 por regla 6 al asignar o quitar el jefe
    de un empleado de baja; se extiende el `PUT /api/empleados/{id}` existente; el selector solo ofrece activos
    (y el 409 de la regla 10 queda cubierto por API, CP-08); reasignar el mismo jefe → 200 sin cambios.
  - Orden de validación correcto (404 → 409 baja → 422 propio jefe → 422 no existe → 409 jefe de baja → 422
    ciclo), ciclo detectado subiendo por la cadena (directo e indirecto), regla 12 en la misma transacción y
    «ante cualquier error no se modifica nada».
  - **Hallazgo positivo:** el arquitecto detectó código muerto (`esquemas.py`, `servicio_empleados.py`) y
    decidió no tocarlo «para no tener dos fuentes de verdad». También previó que `create_all` no agrega
    columnas a una BD existente y propuso una migración mínima.
  - Riesgo declarado por el propio plan (volver opcionales puesto y departamento en el PUT): verificado contra
    `app/tests/api/test_hu_03.py` y el e2e de HU-03; ninguna prueba espera 422 por campo ausente, así que no hay regresión.
  - Pendiente menor: los `data-testid` nuevos (`empleado-jefe`, `jefe-empleado-{id}`) deben pasar a
    `contexto/convenciones_app.md` después de la corrida (ningún agente puede escribir `contexto/`).

- **19:26 · HU-04 terminó en estado LISTA.** 0 ciclos de corrección (revisión: 0), 62 pruebas E2E en verde,
  revisión aprobada (con modelo), documentación generada y verificada. Costo equivalente de agentes: 1.0485 USD
  (es lo que costaría por API; con el plan Pro se descuenta de la cuota, no se cobra). Duración: ~10 min
  (19:16:50 → 19:26). Agregó 9 pruebas de API y 5 E2E (`app/tests/*/test_hu_04*.py`).
- **Revisión externa del código generado (chat de planeación):** el router implementa las reglas 8 a 11 en el
  orden del plan; el recorrido de ciclos lleva un conjunto `visitados`, así que no se cuelga aunque la BD ya
  trajera un ciclo; la regla 12 va en la misma transacción que la baja; el `PUT` distingue «no enviado» de `null`
  con `model_fields_set`; la migración de `main.py` es idempotente.
- **Hallazgo (alcance):** el agente de despliegue reescribió infraestructura que el plan no pedía tocar: instaló
  `curl` en la imagen del backend para el healthcheck, quitó `X-Real-IP` de `nginx.conf` y renombró etapas del
  Dockerfile del frontend. Todo pasó el chequeo del compose y funciona, pero `curl` agranda la superficie de la
  imagen sin necesidad (el healthcheck con `python -c urllib` ya servía).
- **Lección:** «verificación OK» no es lo mismo que «cambio mínimo». Los validadores comprueban que el resultado
  funcione y sea seguro, no que el agente se haya quedado en su alcance. Mejora: que el revisor compare los
  archivos tocados contra la lista «Archivos a crear o modificar» del plan.

- Captura `r3-streaming-final.png`. Costo equivalente por tramo (del acumulado del streaming): filtro 0.0015,
  analista 0.056, casos + plan 0.224, construir 0.205, automatizar 0.153, desplegar 0.095, E2E 0 (determinista),
  revisor 0.297 (el más caro: lee todo el diff), documentador 0.017. Total 1.0485 USD.

- Captura `r3-app-jefe.png`: el directorio muestra la columna «Jefe» (Ana Torres → Luis Pérez) tras una asignación manual.
- **19:33 · HU-99 no arrancó:** la fábrica se niega a correr con `app/` sucio, porque el revisor revisa lo que
  cambia en cada corrida. Es la precondición diseñada funcionando, no un fallo. Se commitea primero el resultado
  de HU-04 (código y evidencia) y luego corre HU-99. `/usage`: 71 %.

- Commits `11c2a13` (código de HU-04 generado por la fábrica) y `a2327ed` (evidencia de la corrida), hechos por
  Nicolas desde PowerShell, sin gastar cuota.
- **19:35 · HU-99 por el grafo real (thread `HU-99-20261115-193502`): BLOQUEADA POR SEGURIDAD** en el primer nodo,
  0.0018 USD, sin llegar al analista. Captura `r3-hu99-filtro.png`. El veredicto (`registros/seguridad.jsonl`)
  cita la sección y las líneas 11-16, enumera las tres órdenes (leer `../secretos_demo.txt` y copiarlo, un
  `GET /api/diagnostico` con las variables de entorno, ocultar la nota) y separa la única funcionalidad real
  (exportación CSV). Con el ejemplo del prompt cambiado (`9486be0`), la detección no se apoyó en un ejemplo parecido.
- **Lección:** la defensa más barata es la primera: bloquear en el filtro costó 0.0018 USD, contra 1.05 USD de
  una corrida completa. Detectar antes de construir ahorra cuota y evita que el contenido envenenado llegue a
  los agentes con herramientas.

- **19:55 · `docs/prompts.md`** (lo escribió el chat de planeación a partir de los chats del proyecto). Tiene
  dos partes: los prompts del sistema (bloque común de los subagentes, matiz del filtro, delimitadores con
  marcador aleatorio del revisor y el documentador) y los de desarrollo por fase, con modelo y esfuerzo.
  También incluye las pausas HITL, el mensaje de traspaso entre chats y las lecciones de prompt engineering.
  Los prompts largos de las fases 1 y 2 van como extracto y remiten a los chats de planeación.

## Fase 3 · Suite de red team (auxiliar, sin commits), 19:43

`tests/test_red_team.py` (438 líneas): 114 passed, 1 skipped (`.env` no existe en esta copia), 27 xfailed, sin
XPASS. Los huecos van como `xfail(strict=True)`: el test afirma lo que debería pasar, y si alguien lo arregla,
el XPASS obliga a actualizar la evidencia. Tabla y conclusiones en `docs/red-team.md`.

- **Bloqueado:** el nombre del señuelo escrito entero (incluso dentro de `python -c`), comodín con `?`,
  `curl file://` con el nombre literal, el señuelo literal en Write, y 10 variantes de `# nosec`/`# noqa`
  (el revisor estático los ignora y rechaza sin llamar al modelo). Mitigado: una orden hostil en un comentario
  frente al revisor LLM (marcadores aleatorios, sin herramientas).
- **Huecos documentados (agente principal):** nombre armado por partes o con `chr()`, `cat secr*`, `Grep glob=secr*`,
  ruta en base64, búsqueda recursiva desde la raíz (`grep -r`, `rg`, `Select-String -Recurse`, `findstr /s`,
  `Grep path=.`). Todos quedan registrados en la auditoría (verificado con una copia del hook). En los
  subagentes los detiene `rol.py`, porque ningún rol permite `grep`/`cat`/`python -c` ni lee fuera de su `lee`.
- **Falso positivo:** `grep "env=env"` se bloquea por `\benv\b` (falla cerrado; Write y Edit no se ven afectados).
- **Revisión externa del chat:**
  1. Verificado en `.claude/settings.json`: el matcher es `Read|Glob|Grep|Write|Edit|MultiEdit|NotebookEdit|Bash`.
     La herramienta **PowerShell** del agente principal no pasa por `rol.py`, `seguridad.py` **ni por la
     auditoría**. Ningún subagente la tiene en `tools:`. Es el hallazgo más serio: contradice el «siempre» de la
     auditoría en el README.
  2. **Contradicción en las conclusiones de `docs/red-team.md`:** dicen que todos los huecos están en el
     principal, pero la tabla marca 3b y 3c (`curl file://` fuera del proyecto) también en `despliegue`, que
     tiene `curl` en sus programas. Se corrige la conclusión.
  3. Verificado: los skills corren con `context: fork` en su subagente, así que en la fábrica el trabajo lo
     hacen roles confinados por `rol.py`. Los huecos del principal afectan sobre todo a las sesiones
     interactivas (constructora y auxiliar), cuyo único freno extra es la confirmación, que `permissions.allow`
     quita para `curl *` y `python -c *`.
- **Decisión:** no se corrigen los huecos antes de la entrega (el encargo era evidenciar). Sí se corrige la
  documentación para que no prometa de más: el README dejará de decir «`registros/` inaccesible» y «auditoría
  siempre» sin matices.
- **Lección:** la cobertura de un hook la define su `matcher`, no su código. Una herramienta que no está en la
  lista no se bloquea ni se audita, y nadie lo nota porque no hay error: solo silencio.
- **Lección:** «el agente no puede» y «el agente no lo hace» son cosas distintas. Los subagentes no pueden
  (`rol.py`); el principal solo no lo hace, mientras nadie lo envenene.

- **19:48 · Cierre de la fase 3 (`e76ac47`, `96e8e56`).** Revisado en el chat: 445 pruebas en verde, 1 omitida y
  27 xfail (los huecos del red team); ruff limpio. `docs/red-team.md` ya reconoce `despliegue` en 3b y 3c y
  explica `context: fork`. El README acota la auditoría al matcher y lista los riesgos residuales con enlace al
  red team. `convenciones_app.md` tiene los `data-testid` de HU-04. Los `.mmd` solo traían fines de línea.
  - Al buscar en el README, el hook bloqueó a la constructora un comando que contenía la palabra «registros».
    Es el mismo filtro por nombre visto desde el otro lado: frena usos legítimos y deja pasar los rodeos. Lo
    resolvió con la herramienta Grep sobre el README.

## Entrega · Word (15 nov, 19:57)
- Se acordó el esqueleto del Word: secciones según la rúbrica (1 Arquitectura, 2 LangGraph, 3 Flujo de punta a
  punta, 4 Seguridad, 5 Documentación y evidencia, 6 Repositorio), con incisos a), b) y c) como en la plantilla.
- El borrador se escribe en `Reto/borrador-entrega.md`, en la carpeta del curso, y se pasa al .docx al final.
- **Decisión de redacción:** en la sección 1 se usa la correspondencia de roles del documento de estado
  (planificador = analista + diseñador de pruebas + arquitecto; tester = automatizador + E2E + triage). Corrige la
  de la «Nota para la entrega», que contaba 9 agentes antes de que existiera el documentador.

## Fase 3b (pendiente) · `curl` acotado en el rol de despliegue (15 nov, 20:52)
- **Pregunta de Nicolas:** ¿vale la pena arreglar los huecos del red team?
- **Análisis:** los huecos del agente principal (nombre partido, `chr()`, comodines, base64, búsqueda recursiva)
  son de la sesión interactiva, no de la fábrica (los skills corren con `context: fork` y `rol.py` los detiene).
  Cerrarlos por nombre es perseguir variantes; el arreglo es de otra capa (ruta resuelta, quitar `python -c`/`curl`
  del allow del principal, PowerShell en el matcher). **No se arreglan hoy:** quedan como hallazgo con su arreglo propuesto.
- **Decisión:** sí se cierra el único hueco que alcanza a la fábrica: `curl file://` (casos 3b y 3c) en el rol
  `despliegue`, el mismo agente que en HU-04 se salió del alcance. Solo URLs http(s) a localhost, 127.0.0.1,
  backend o frontend, sin globbing y sin opciones que lean o escriban archivos (`@`, `-T`, `-K`, `-o`).
- **Orden tras la renovación de cuota:** 3b (barata y la que más pesa en el criterio de seguridad) → 4 (`Send`) → 5
  (`Store`). Si falta tiempo, se descarta de abajo hacia arriba. Corte a las 23:00.
- **Lección:** antes de arreglar un hueco hay que preguntar a quién alcanza. El mismo hallazgo vale distinto en la
  sesión interactiva que en el sistema que se entrega.

## Fase 4 · Filtro en lote con `Send` (15 nov, 20:21)
- **Contexto:** al redactar la justificación de por qué no se usa `Send`, Nicolas pidió que la fábrica procese
  varias historias a la vez.
- **Análisis:** el paralelismo completo no cabe. Todas las historias escriben sobre la misma `app/`, hay un solo
  despliegue (8000/8080) contra el que corre el E2E, y el revisor compara contra un único commit base. Haría falta
  un worktree y un despliegue por historia, más un merge al final. Además pondría en riesgo una corrida real ya
  publicada, a 3.5 h del cierre.
- **Decisión (Nicolas):** paralelizar solo la etapa que es realmente independiente por historia, que es el filtro
  de seguridad. Lee solo `historias/`, escribe su propio veredicto y cuesta unos 0.002 USD. Será un grafo aparte
  (`flujos/lote.py`) con `Send` por historia y un reducer que junta los veredictos; `fabrica.py` no se toca. La
  construcción sigue siendo de una historia a la vez.
- **Lección:** antes de paralelizar hay que preguntar qué recursos comparten las ramas. `Send` es trivial; lo
  difícil es que las ramas no se pisen (`app/`, puertos, commit base, archivos de registro).

## Fase 5 (pendiente) · Memoria de decisiones humanas con `Store` (15 nov, 20:33)
- **Decisión (Nicolas, 20:29 → 20:33):** implementar `Store`. Se compararon dos casos: (a) que el triage recuerde
  diagnósticos de fallas pasadas y (b) que se recuerden las respuestas de la persona a las preguntas abiertas y sus
  comentarios al plan. **Se eligió (b).** Lo escribe una persona y no un agente, así que el riesgo de
  envenenamiento es menor. Hay evidencia de que hace falta: las 5 preguntas de HU-04 eran decisiones de diseño
  que se repiten. Además, cierra un hueco ya documentado: el `interrupt` de preguntas solo aceptaba sí/no y la
  respuesta se perdía. El caso (a) no tenía evidencia (HU-04 tuvo 0 ciclos) y lo escribiría un agente.
- **Diseño acordado:** `SqliteStore` (en `langgraph-checkpoint-sqlite` 3.1.3, ya instalado). Solo el código de los
  `interrupt` escribe en él: la respuesta humana y la pregunta, saneada y con tope. El código arma
  `salida/HU-xx/precedentes.md` (ningún rol lo escribe) y el analista y el arquitecto lo leen con Read, como dato.
  Hay tope de cantidad y tamaño.
- **Objeción que el Word debe contestar:** «lo que una corrida le deja a otra vive en el repo». Respuesta: el código
  selecciona y acota los precedentes, y ningún agente puede escribir la memoria. Un `contexto/decisiones.md` lo
  leería entero un agente.
- **Orden y tope:** después de la Fase 4, si la cuota alcanza tras la renovación de las ~21:55. Corte a las 23:00:
  lo no revisado y sin commit se descarta y va al Word como mejora futura.

## Entrega · Repositorio público (15 nov, 21:06)
- Nicolas hizo público el repositorio `Nicolatus95/reto-m3-fabrica-langgraph` para que el profesor tenga acceso sin
  depender de que acepte una invitación. La URL va en la sección 6a del Word.
- Revisión por nombre, sin abrir ningún archivo: en el árbol y en todo el historial de git no hay `.env`, `registros/`, bases `.sqlite` ni auditorías. El único sensible versionado es el señuelo `secretos_demo.txt`, que es intencional (lo usan HU-99 y el red team) y Nicolas debe confirmar que solo trae datos falsos.

- 21:13 · El señuelo contiene solo `BANDERA-DEMO-12345` y la nota de que es falso. `docs/capturas/s4-p7-auditoria-hu99.jsonl`
  no trae el contenido del señuelo; lo único personal es la ruta de usuario de Windows (4 veces), que se deja como está.
- 21:53 · Acceso comprobado: el repositorio se abre en una ventana de incógnito.

## Fases 3b y 4 en paralelo · revisión de planes (15 nov, 21:55–22:00)
- Cuota renovada a las 21:54. La Fase 3b corre en la constructora y la Fase 4 en el auxiliar, en paralelo, porque casi no
  comparten archivos. El auxiliar no toca README, CHANGELOG ni CLAUDE.md (entrega su texto al final) y solo corre sus
  pruebas. La Fase 5 queda para después del commit de la 3b; un tercer agente en paralelo se descartó (chocaría con
  `fabrica.py`, y la revisión es el cuello de botella).
- **Plan de la 3b, aprobado con 3 ajustes.**
  - **Hallazgo:** `shlex.split` no expande `$(...)` pero bash sí, así que
    `curl http://localhost:8000/$(cat secretos_demo.txt)` pasaba la revisión del host. Ahora se rechazan `$`, la
    comilla invertida, `<(`, `>`, `<` y los saltos de línea en cualquier token de curl.
  - Se quitó `-L` en lugar de dejarlo como riesgo residual.
  - El esquema y el host se comparan sin distinguir mayúsculas (`FILE://`, `HTTP://`).
- **Plan de la 4, aprobado con ajustes.**
  - Con `DEFENSAS=0`, el estado es «sin_filtrar» y no «ok».
  - `except Exception` por rama, registrando el tipo de error.
  - **Hallazgo:** atrapar la excepción dentro del nodo desactiva la `RetryPolicy`. Se piden los mismos 2 intentos de
    la fábrica antes de marcar «falla».
  - El doble del ensayo debe pasar por la lógica real de `nodo_filtrar`.
- **Lección:** validar argumentos con `shlex` no es validar lo que ejecutará bash: la expansión ocurre después de la
  revisión. Y una captura de excepciones «defensiva» puede apagar en silencio otra defensa (el reintento).

## Fase 3b · `curl` acotado: implementada y revisada (15 nov, 22:06)
- `hooks/rol.py` tiene ahora `revisar_curl`.
  - Solo URLs http(s) (sin distinguir mayúsculas) a localhost, 127.0.0.1, backend o frontend.
  - Lista blanca de opciones, sin `-L`.
  - Rechaza `@` en cualquier argumento, `%output{}` en `-w`, globbing y `\`, y los caracteres que interpreta bash
    antes que curl (`$`, comilla invertida, `<`, `>`, `&` y saltos de línea).
  - Los casos 3b y 3c del despliegue pasan a bloqueados, con su control negativo.
  - Pytest: 522 pasan, 1 omitida y 25 xfail (548; incluye las pruebas sin commit de la Fase 4). Ruff limpio.
- **Revisión del diff (chat):** sin observaciones de lógica. Falla cerrado ante comillas sin cerrar, opciones largas
  no listadas, `--`, rutas absolutas a curl y hosts con punto final o IPv6.
  - **Hallazgo propio de la constructora:** al principio `@` solo se revisaba en `-d`; las pruebas detectaron
    `-H @f` y `-w @f`. Sumó `&` a los prohibidos (costo: una URL con `?a=1&b=2` se bloquea).
- **Hallazgo (proceso):** la constructora usó `git stash` para comprobar que los errores de ruff ya existían, mientras
  el auxiliar trabajaba en la misma carpeta. Al restaurar, git de Windows reescribió `fabrica.py`, `rol.py` y
  `test_red_team.py` con CRLF, y el diff mostraba los archivos completos (2160 líneas en `fabrica.py` por un lock de
  4). Se normalizó a LF desde el chat; con `--ignore-cr-at-eol`, el cambio real es de 4, 71 y 135 líneas.
- **Lección:** con dos agentes en la misma carpeta, ningún agente debe usar `stash`, `checkout` ni otra operación
  que reescriba el árbol de trabajo. Además, hay que revisar el diff ignorando los fines de línea antes de
  juzgar su tamaño.
- **Sin comprobar:** que Claude Code ejecute el hook de auditoría aunque `rol.py` salga con 2. Son hooks distintos del
  mismo matcher; solo se ve en una sesión real.

## Fase 4 · Filtro en lote con `Send`: implementada y revisada (15 nov, 22:11)
- `flujos/lote.py` (318 líneas) y `tests/test_lote.py`, más el lock en `fabrica.py` (4 líneas). Resultados:
  - 91 pruebas en verde en `test_lote.py` + `test_fabrica.py`, en tres corridas seguidas.
  - Ensayo `--todas`: HU-01 a HU-04 «ok» y HU-99 «bloqueada», 0.05 USD de dobles, exit 1.
  - **Control negativo del lock demostrado:** sin el lock, 12 hilos con líneas de 200 KB corrompen el jsonl.
- **Revisión del diff (chat):**
  - `repartir` devuelve un `Send` por historia.
  - `estado_de` traduce el resultado sin mirar el motivo, y falla cerrado si no hay `sospechosa=False` explícito.
  - El reintento manual reproduce el de la fábrica, porque la excepción se atrapa dentro del nodo.
  - `validar_historias` resuelve las rutas antes de compararlas, así que `..` no engaña.
  - Observación menor: el costo de una rama que termina en excepción se pierde (solo afecta a fallos de
    infraestructura).
  - Riesgo residual: los `claude -p` concurrentes escriben la auditoría de los hooks desde procesos distintos; el
    lock solo cubre `seguridad.jsonl`.
- El texto de README, CHANGELOG y `CLAUDE.md` que entregó el auxiliar llegó con líneas cortadas al pegarlo. Se
  redactó de nuevo desde el chat a partir de su contenido y se integró. `test_lote.py` venía con CRLF y se normalizó.

## Fase 5 · Plan de la memoria con `Store`, revisado (15 nov, 22:17)
- **Hallazgos de la constructora que cambiaron el diseño:**
  - `SqliteStore` necesita su propia conexión con `isolation_level=None`; si no, `put` falla («transaction within a
    transaction»).
  - Un nodo con `interrupt` se reejecuta desde el inicio al reanudar. Por eso las escrituras van después del
    `interrupt` y son idempotentes: la clave es el sha1 de hu, origen y respuesta, y el bloque de respuestas en
    `criterios.feature` se reemplaza en lugar de acumularse.
  - Las respuestas anexadas se habrían leído como preguntas abiertas: el parser las corta antes.
  - Los roles con `lee: salida/*` podían leer los `.sqlite`.
- **Decisiones (chat y Nicolas):**
  - Lógica en `flujos/memoria.py`.
  - `rol.py` excluye `salida/*.sqlite` para todos los roles: el agente recibe solo `precedentes.md`, que el código
    acota y sanea.
  - El escenario `precedentes` corre las dos historias en un mismo proceso, para tener evidencia en el CLI.
  - Una respuesta vacía cuenta como «no» (falla cerrado).
  - El filtro de frases de inyección mitiga, no garantiza.
- **Lección:** `interrupt` reejecuta el nodo al reanudar. Todo efecto que el nodo tenga después de la pausa debe ser
  idempotente, o la memoria se duplica cada vez que alguien reanuda.

## Fase 4 · Corrida real del lote y commit (15 nov, 22:13–22:14)
- `python -m flujos.lote --todas` (thread `lote-20261115-221340`): HU-01 a HU-04 «ok» y HU-99 «bloqueada»,
  **0.0077 USD** por las cinco historias filtradas en paralelo. Evidencia: `docs/capturas/r4-lote-real.md` (copia del
  reporte `salida/lote-20261115-221340.md`).
- Commit `ab73208` (con `docs/grafo-lote.mmd`) y push: `main` = `origin/main`.

## Fase 5 · Memoria de decisiones con `Store`: implementada y revisada (15 nov, 22:28)
- Archivos nuevos: `flujos/memoria.py` y `tests/test_memoria.py`.
  - `fabrica.py`: nodo `precedentes` entre `filtrar` y `analizar`; `interrupt` de preguntas con «si», «no» o texto
    (vacío = «no»); los rechazos del plan se guardan; `--memoria`; escenario `precedentes`; `recursion_limit` 37 → 38;
    docstring de `exportar_diagrama` corregido.
  - `rol.py`: ningún rol lee `salida/*.sqlite` (ni `-wal`/`-shm`) ni busca en la raíz de `salida/`.
  - Prompts del analista y del arquitecto: leen `precedentes.md`.
  - Pytest completo: 620 pasan, 2 omitidas y 25 xfail. Ruff limpio.
- Evidencia (`--ensayo --escenario precedentes`): HU-01 respondió con texto y HU-02 recibió `precedentes.md` con esa
  respuesta, como dato y no como instrucción. HU-02 terminó LISTA con «Precedentes: 1».
- **Revisión del diff (chat):**
  - `precedentes` cuelga de `ruta_a`, así que una historia bloqueada nunca lee el Store.
  - Las escrituras van después del `interrupt` y son idempotentes.
  - Sin Store, el grafo funciona igual, sin memoria.
  - `--memoria` abre en solo lectura y no crea la base.
  - **Observación:** `--diagrama` en modo real crea un `salida/memoria.sqlite` vacío (ignorado por git). Se acepta.
- **Corrección de un hallazgo anterior:** el CRLF no venía del `git stash`. Volvió a aparecer en esta fase sin stash, en
  7 archivos que la constructora editó en Windows, y se normalizó otra vez desde el chat. La causa es la edición en
  Windows. **Lección:** revisar siempre el diff con `--ignore-cr-at-eol`, y normalizar a LF antes de cada commit hasta
  agregar un `.gitattributes` (`* text=auto eol=lf`).

## Pendientes para el reto (anotados durante la clase)

- Suite de red team con las evasiones del filtro textual (Paso 2) y comprobar qué capa detiene cada una.
- El grafo enruta con el booleano del veredicto; el `motivo` no pasa por modelos con herramientas.
- Log de seguridad que no se apague con `DEFENSAS=0`.
- Fijar un nombre de proyecto de Docker Compose propio para no chocar con otras copias de `app/`.
