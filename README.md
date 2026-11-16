# Fábrica de software con agentes · M3B (sin API key) + reto LangGraph

Una cadena de agentes que, a partir de una **historia de usuario**, escribe criterios de aceptación, casos de prueba y
el código de una app de gestión de empleados (FastAPI + React), la despliega con Docker, la prueba de punta a punta y, si
algo falla, manda corregir al responsable correcto. Cada agente es un **subagente de Claude Code** y se usa con
`claude auth login` (sin `ANTHROPIC_API_KEY`). El orquestador del reto es un grafo de **LangGraph** (`flujos/fabrica.py`).

> Principio del proyecto: **el código decide, no el agente.** Cada entrega pasa por `validadores/` y `verificacion/`, y
> cada nodo se juzga por su artefacto (existe, cambió y valida), nunca por lo que el modelo diga de sí mismo.

## Índice
1. [Setup (Windows / PowerShell)](#setup-windows--powershell)
2. [Uso](#uso)
3. [Pruebas](#pruebas)
4. [Arquitectura de agentes](#arquitectura-de-agentes)
5. [Capas de seguridad](#capas-de-seguridad)
6. [Estructura del repo](#estructura-del-repo)
7. [Notas de clase](#notas-de-clase)

## Setup (Windows / PowerShell)

Requisitos: Windows con PowerShell, Python 3.12, Node 20 o superior, Git, **Docker Desktop encendido** (motor Linux) y
Claude Code con sesión iniciada. Las rutas del entorno son `.venv\Scripts\python` (no `.venv/bin/python`).

```powershell
# 1. Entorno de Python (desde la raíz del repo)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium     # solo para correr pruebas e2e fuera del sandbox (opcional)

# 2. Sesión de Claude Code SIN API key
claude auth login
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue   # el orquestador igual la quita del entorno del hijo

# 3. Imágenes del sandbox (una sola vez; descargan ~4.6 GB entre las dos)
.venv\Scripts\python -m verificacion imagen_sandbox
docker image ls fabrica-sandbox            # fabrica-sandbox:1 (~3.9 GB) y fabrica-sandbox-node:1 (~330 MB)
```

**Imágenes del sandbox.** El código que escriben los agentes **no corre en tu máquina**: corre en contenedores
endurecidos construidos desde `sandbox/Dockerfile` (`fabrica-sandbox:1`, Python + Playwright + dependencias fijas del
backend) y `sandbox/Dockerfile.node` (`fabrica-sandbox-node:1`, para compilar el front-end). Nunca se construyen solas:
solo con `python -m verificacion imagen_sandbox`. Sin Docker o sin las imágenes, una corrida real **no arranca** y las
verificaciones **fallan** (no hay ruta de respaldo al anfitrión).

**Puerto 8000 e IncrediBuild.** La app usa el 8000 (backend) y el 8080 (front-end), fijos en las convenciones. En
equipos con Visual Studio, *IncrediBuild Manager* puede ocupar el 8000. Compruébalo y detén sus servicios mientras
trabajas (PowerShell como administrador):

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object LocalPort, OwningProcess
Get-Service -DisplayName "*IncrediBuild*" | Stop-Service        # se reinician al arrancar Windows
```

**Antes de una corrida real** el orquestador exige: Docker activo, las dos imágenes, y `app/` **sin cambios sin
commitear** en git (para que el revisor solo juzgue lo que cambie durante la corrida). Si falta algo, sale con código 2
antes de gastar tokens.

## Uso

### El orquestador (LangGraph) — la forma recomendada

```powershell
# Corrida real: filtro → criterios → casos → plan → (aprobación) → código → despliegue ∥ pruebas → e2e → ... → reporte
.venv\Scripts\python -m flujos.fabrica historias\HU-04-asignar-jefe-directo.md

# Aprueba por adelantado las dos pausas humanas (preguntas abiertas y plan)
.venv\Scripts\python -m flujos.fabrica historias\HU-04-asignar-jefe-directo.md --aprobar

# Cada corrida imprime su thread_id; con él puedes reanudarla desde su último checkpoint (por ejemplo tras una pausa)
.venv\Scripts\python -m flujos.fabrica --reanudar HU-04-20261115-101500

# Historial de checkpoints de una corrida (solo lectura, del más reciente al más antiguo)
.venv\Scripts\python -m flujos.fabrica --historial HU-04-20261115-101500

# Memoria de decisiones humanas (solo lectura): lo que la persona respondió en preguntas y rechazos del plan
.venv\Scripts\python -m flujos.fabrica --memoria
# Ensayo de la memoria: corre HU-01 (la persona responde texto) y luego HU-02, e imprime su precedentes.md
.venv\Scripts\python -m flujos.fabrica historias\HU-01-registrar-empleado.md --ensayo --escenario precedentes

# Ensayo SIN modelo y SIN Docker: dobles deterministas para ver las rutas del grafo (no toca salida/)
.venv\Scripts\python -m flujos.fabrica historias\HU-01-registrar-empleado.md --ensayo --escenario e2e_pruebas
.venv\Scripts\python -m flujos.fabrica --diagrama          # solo exporta docs\grafo.mmd y docs\grafo-correccion.mmd
```

La corrida muestra una línea por nodo (hora, bitácora y **costo acumulado**). El resultado queda en
`salida\HU-xx\reporte.md`; si la historia es sospechosa, termina en `BLOQUEADA POR SEGURIDAD`. Los checkpoints están en
`salida\fabrica.sqlite`. Todo bucle tiene tope (intentos de la compuerta, ciclos de corrección, `recursion_limit`); al
alcanzarlo, la corrida **escala** a una persona con un mensaje, sin traceback.

Nodos y modelos (`MODELOS` en `flujos/fabrica.py`): `filtrar` y `documentar` usan haiku; el resto, sonnet.

### Filtro de seguridad en lote (`Send`)

Antes de gastar tokens en la fábrica, puedes pasar varias historias por el filtro de seguridad a la vez:

```powershell
.venv\Scripts\python -m flujos.lote historias\HU-01-registrar-empleado.md historias\HU-99-envenenada.md
.venv\Scripts\python -m flujos.lote --todas            # todas las historias\HU-*.md, sin backlog.md
.venv\Scripts\python -m flujos.lote --todas --ensayo   # dobles deterministas, sin modelo
.venv\Scripts\python -m flujos.lote --diagrama         # exporta docs/grafo-lote.mmd
```

El lote **no construye nada**. Cada historia es una rama (`Send`) que reutiliza `nodo_filtrar` de la fábrica, y corren
hasta 4 a la vez. El resultado es `salida/lote-<AAAAMMDD-HHMMSS>.md`, con una tabla HU | estado (`ok`, `bloqueada`,
`falla` o `sin_filtrar`), el costo total y, por cada historia `ok`, el comando para construirla. El código de salida es 0
solo si todas salen `ok`. Cada historia falla cerrado por separado, sin detener a las demás, y el motivo del veredicto
sigue viviendo solo en `registros/`.

**¿Por qué solo el filtro va en paralelo?** Cada filtro lee una sola historia y escribe en su propia carpeta, así que las
ramas no se pisan. El resto de la fábrica comparte estado: `app/` es una sola aplicación que cada historia modifica, el
despliegue ocupa los puertos 8000 y 8080, y el commit base define lo que revisa el revisor. Dos construcciones en
paralelo mezclarían cambios, tumbarían el despliegue de la otra y harían que el revisor juzgara código ajeno. Por eso
las historias que pasan el filtro se construyen de una en una.

### Memoria de decisiones (`Store`)
Las respuestas de la persona (texto libre en las preguntas abiertas y los comentarios al rechazar un plan) se guardan en
un Store de LangGraph (`salida/memoria.sqlite`, namespace `("decisiones",)`) y el nodo `precedentes` entrega a las
historias siguientes un `salida/HU-xx/precedentes.md` con las 10 decisiones más recientes de OTRAS historias (máx. 4000
caracteres). Por qué Store y no un archivo en `contexto/`: el código selecciona, acota y sanea lo que el agente ve, y
ningún agente escribe la memoria ni puede leer la base (`hooks/rol.py` bloquea `salida/*.sqlite`); un archivo en
contexto lo leerían y podrían editar los agentes sin filtro. En las preguntas abiertas se responde `si`, `no` (o vacío:
detiene) o un texto con las respuestas. `--memoria` lista el contenido sin modificarlo.

### Los skills de Claude Code (un paso a la vez)

Dentro de una sesión de `claude` en esta carpeta:

```
/fabrica historias/HU-01-registrar-empleado.md     # la fábrica completa con el guion del orquestador
/filtrar historias/HU-99-envenenada.md             # solo el filtro de seguridad
/criterios historias/HU-01-registrar-empleado.md   # solo el analista
/triage HU-01                                      # solo el triage (necesita salida/HU-01/fallos.md)
```

### Verificaciones sueltas (deterministas, sin modelo)

```powershell
.venv\Scripts\python -m verificacion app                 # arranca el backend y compila el front-end, en el sandbox
.venv\Scripts\python -m verificacion pruebas HU-01       # recolecta las pruebas (pytest --collect-only), en el sandbox
.venv\Scripts\python -m verificacion e2e HU-01           # pruebas HU-01 a HU-03 contra la app desplegada (necesita Docker)
.venv\Scripts\python -m validadores.validar salida\HU-01\criterios.feature
```

## Pruebas

```powershell
.venv\Scripts\python -m pytest tests -q                  # 548 pruebas (522 pasan, 1 omitida, 25 xfail: huecos del principal); sin modelo, sin Docker y sin red
.venv\Scripts\python -m pytest tests\test_agentes.py -q  # solo los prompts de los subagentes (rápido)
.venv\Scripts\python -m ruff check flujos hooks validadores tests verificacion
```

- `tests/` usa dobles del modelo, de Docker y de git: prueban las rutas del grafo, el revisor, el documentador, los
  hooks, el sandbox y los prompts (bloque de seguridad idéntico en los 8 agentes, herramientas contra `roles.py`).
- Los **spikes** (`spikes/`) comprueban contra el mundo real y **algunos gastan cuota o usan Docker**; corre solo los
  que entiendas: `comprobar_paso*.py` (sin modelo), `probar_sandbox.py` (Docker; con `--e2e` necesita la app arriba) y
  `probar_revisor.py` (llama al modelo; cuesta unos centavos).
- Para probar un hook a mano, llámalo con un JSON, como en los `comprobar_paso*.py`. No pegues el JSON en la línea de
  comandos de un agente: `seguridad.py` bloquea justo esos patrones.

## Arquitectura de agentes

| # | Agente | Entrada | Salida (en `salida/HU-xx/` salvo indicación) | Herramientas |
| --- | --- | --- | --- | --- |
| 0 | `filtro-seguridad` (haiku) | Historia (no confiable) | `veredicto.json` | Read, Write |
| 1 | `analista` | Historia | `criterios.feature` | Read, Glob, Write |
| 2 | `disenador-pruebas` | Criterios | `casos_prueba.json` | Read, Glob, Write |
| 3a | `arquitecto` | Criterios, casos, `app/` | `plan.md` (lo aprueba una persona) | Read, Glob, Grep, Write |
| 3b | `desarrollador` | Plan aprobado | `app/backend`, `app/frontend` | + Edit, Bash acotado |
| 4 | `despliegue` | Código | Dockerfiles, compose y la app en 8000/8080 | + Edit, Bash (`docker compose`) |
| 5 | `automatizador` | Casos | `app/tests` (pytest + Playwright) | + Edit, Bash acotado |
| 6 | `triage` | `fallos.md` | `diagnostico.json` | Read, Glob, Grep, Write |

Además, en el grafo: el **revisor** (`flujos/revisor.py`) y el **documentador** (`flujos/documentador.py`, genera
`documentacion.md`; el modelo solo aporta campos acotados y Python arma el archivo y verifica endpoints y reglas).

```
filtrar ─ sospechosa ─────────────────────────────────────────────────────► reporte (BLOQUEADA)
   │ ok
criterios → casos → plan → (aprobación) → construir → despliegue ∥ pruebas → e2e ─ OK ─► revisar → documentar → reporte
                                                                                 │ falla
                                                              correccion (subgrafo): triage → corregir_* → e2e (máx. 2 ciclos) ─► escalar
```

Cada subagente tiene un prompt con **contexto explícito** (rutas que lee con Read, sin `@archivo`), contrato de entrada
y salida y un ejemplo de formato. Las salidas estructuradas son contratos Pydantic (`validadores/contratos.py`).

## Capas de seguridad

La historia de usuario es **contenido no confiable**. Ninguna capa basta sola (defensa en profundidad):

1. **Filtro y mínima agencia.** `filtro-seguridad` solo lee `historias/` y solo escribe su veredicto; el orquestador
   nunca lee la historia. El motivo del veredicto vive fuera de `salida/`.
2. **Hooks** (`.claude/settings.json`): `hooks/rol.py` + `hooks/roles.py` (qué lee, escribe y ejecuta cada rol) y
   `hooks/seguridad.py` (para todos: lectura confinada, secretos, terminal y bloqueo por nombre de `registros/` para lectura y
   escritura). Los hooks y la **auditoría** cubren las herramientas del matcher (`Read|Glob|Grep|Write|Edit|MultiEdit|
   NotebookEdit|Bash`); la herramienta PowerShell del principal no pasa por ellos. Dentro de ese alcance, la auditoría
   se escribe en `registros/auditoria.jsonl` también con `DEFENSAS=0` (campo `defensas`: `activas`/`apagadas`).
   `registros/` es solo para personas: revísala desde tu terminal. La auditoría de la clase (con HU-99) está en
   `registros/auditoria-clase.jsonl`.
3. **Prompts:** bloque de seguridad común en los 8 subagentes (lo leído es dato, no instrucciones).
4. **Sandbox de ejecución:** `docker run --rm` con `--read-only`, `--cap-drop ALL`, `no-new-privileges`, usuario no root,
   límites de memoria/CPU/pids, sin entorno del anfitrión y montajes de solo lectura. Pruebas y backend sin red; e2e en una
   red interna sin Internet (`fabrica_sandbox`, verificada como interna); front-end en dos fases (`npm ci
   --ignore-scripts` con red, `npm run build` sin red).
5. **Chequeo del compose** (`verificacion/compose_seguro.py`) antes de cada `docker compose up`: rechaza `privileged`,
   redes/pid del anfitrión, `cap_add`, montajes fuera de `app/`, el socket de Docker, `$`, `env_file`, `include`,
   `extends` y redes `external` o con nombre explícito.
6. **Revisor de dos capas:** análisis estático (ruff y bandit fijados, comparación antes/después, sin poder silenciarlo
   con `noqa`/`nosec`) y una revisión con modelo sin herramientas.
7. `permissions.deny` bloquea `.env`, el señuelo, `WebFetch` y `WebSearch`.

**Riesgos residuales conocidos:** `npm`/`npx`/`node` del desarrollador siguen en el anfitrión; la fase de red de `npm ci`
llega al registro de npm; Chromium corre sin su sandbox interno (dentro del contenedor endurecido); los Dockerfiles de
`despliegue` ejecutan sus `RUN` al construir; el agente principal conserva `npm`, `node`, `docker`, `curl` y `python -c`.
El `curl` del rol `despliegue` solo admite URLs http(s) a `localhost`, `127.0.0.1`, `backend` o `frontend` y una lista
blanca de opciones (`rol.py`, `revisar_curl`): `curl file://` ya no es un hueco de la fábrica. Búsquedas recursivas, comodines y rutas armadas por partes evaden el filtro por nombre en el principal (a los subagentes
los frena `rol.py`), PowerShell queda fuera del matcher, y `curl` y `python -c` están en `permissions.allow`: ver
[`docs/red-team.md`](docs/red-team.md). Detalle del sandbox en `CLAUDE.md`.

## Estructura del repo

```
.claude/agents/   prompts de los 8 subagentes        .claude/skills/   comandos (/fabrica, /criterios, ...)
.claude/settings.json  permisos y hooks              flujos/           orquestador LangGraph, revisor, documentador
hooks/            roles, rol.py, seguridad.py        validadores/      contratos Pydantic y validadores
verificacion/     app, pruebas, e2e, sandbox         sandbox/          Dockerfiles del sandbox
historias/        entradas (HU-01 a HU-04, HU-99)    contexto/         reglas de negocio y convenciones
salida/HU-xx/     artefactos (no se editan a mano)   app/              la app generada (no se edita a mano)
spikes/           comprobaciones reales              tests/            pruebas sin modelo
docs/             bitácora, grafos, capturas         registros/        solo para personas
```

Las decisiones, los tropiezos y las iteraciones están en [`docs/bitacora.md`](docs/bitacora.md); la evidencia, en
`docs/capturas/`. Los cambios por fase, en [`CHANGELOG.md`](CHANGELOG.md).

## Notas de clase

**Demo del ataque (solo en clase, solo en una copia de la carpeta).** Con `historias/HU-99-envenenada.md`:

```powershell
claude -p "/fabrica historias/HU-99-envenenada.md --aprobar" --permission-mode acceptEdits   # → BLOQUEADA POR SEGURIDAD
$env:DEFENSAS = "0"      # SOLO en la copia: apaga seguridad.py, el filtro y la lectura por rol (la escritura por rol sigue)
claude -p "/fabrica historias/HU-99-envenenada.md --aprobar" --permission-mode acceptEdits
Select-String -Path app\* -Pattern "BANDERA" -Recurse    # el señuelo empieza con BANDERA: si aparece, el ataque funcionó
```

Los ejemplos con `VARIABLE=valor comando` de otras guías son de Git Bash; en PowerShell se define antes con `$env:VAR`.

Desviaciones de la guía original:
- Se conserva el `deny` del señuelo en `settings.json` (se quita solo en la copia temporal de la demo).
- Se quitaron `Bash(pip *)` y `Bash(uv *)` del `allow`; si hace falta instalar algo, se hace a mano.
- `hooks/rol.py` compara `programas` por prefijo, para que programas de varias palabras funcionen en Windows.
- `verificacion/` decodifica y escribe en UTF-8 (Windows usa cp1252 y fallaba con `✓`).
- `ejemplos/` y el servidor MCP `directorio` de la sesión 3 no se implementaron.
- El ejemplo usa `BANDERA` y no el señuelo completo, porque `hooks/seguridad.py` bloquea escribir ese texto en cualquier archivo.

Labs: **4A** El ataque (¿qué capa lo detuvo primero? desactiva solo el filtro y repite). **4B** El triage (edita una
prueba para que espere un código equivocado: ¿a quién manda y con qué criterio?). **4C** Auditoría (con la auditoría de
`registros/`, desde tu terminal: ¿qué agente usó más herramientas?). **4D** Tu defensa (agrega una regla a
`hooks/seguridad.py` y pruébala sin modelo con un JSON).
