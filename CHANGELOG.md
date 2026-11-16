# Changelog

Todos los cambios importantes del proyecto. Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El proyecto no usa versiones numeradas: las entradas se agrupan por fase y por funcionalidad, y citan los commits.

## [Sin publicar]

Fase 2 del reto, cerrada y sin push.

### Cambiado
- **Fase 3b · `curl` del rol `despliegue`** (`hooks/rol.py`, `revisar_curl`): solo URLs `http(s)` (esquema y host sin
  distinguir mayúsculas) a `localhost`, `127.0.0.1`, `backend` o `frontend`; sin globbing (`{}`, `[]`), sin `@`, sin
  `$`, comilla invertida, `<`, `>`, `&` ni saltos de línea, y con lista blanca de opciones (`-s -S -f -i -I -m/--max-time
  --retry --retry-delay -w -o /dev/null -X GET|HEAD -H`; sin `-L`). Cierra los casos 3b y 3c del red team para la
  fábrica; los del agente principal siguen documentados como `xfail`. `tests/test_red_team.py`: casos nuevos y un
  control negativo (sin la regla, 3b/3c pasan en `despliegue`).

### Añadido
- **Fase 5 · Memoria de decisiones humanas** (`flujos/memoria.py`, `SqliteStore` en `salida/memoria.sqlite`; `InMemoryStore`
  en ensayo y pruebas): `nodo_preguntas` acepta `si`, `no` (o vacío: detiene) o texto libre, que el código anexa a
  `criterios.feature` y guarda; un rechazo del plan también se guarda. Nodo nuevo `precedentes` (tras `filtrar`, así una
  historia bloqueada no recibe memoria) escribe `precedentes.md` con las 10 decisiones más recientes de otras historias
  (tope 4000 caracteres, saneadas). `Estado.precedentes`, `--memoria`, escenario de ensayo `precedentes`,
  `recursion_limit` 37 → 38. `hooks/rol.py`: ningún rol lee `salida/*.sqlite` (ni `-wal`/`-shm`) ni busca en la raíz de
  `salida/`. Los prompts de analista y arquitecto leen `precedentes.md`. `tests/test_memoria.py`.
- **Fase 4 · Filtro de seguridad en lote** (`flujos/lote.py`): grafo `START → repartir (Send) → filtrar_una × N → reunir
  → END` que pasa varias historias por el filtro en paralelo (`max_concurrency=4`) y escribe `salida/lote-<sello>.md`.
  `filtrar_una` reutiliza `nodo_filtrar`; cada historia falla cerrado por separado (`bloqueada`, `falla` con el tipo de
  la excepción, o `sin_filtrar` con `DEFENSAS=0`), con los mismos 2 intentos que la fábrica ante fallos de
  infraestructura. El motivo no entra al estado, al checkpoint (`salida/lote.sqlite`) ni al reporte.
  `registrar_seguridad` se protege con un `threading.Lock`. `tests/test_lote.py`: reparto con 1, 3 y 5 ramas,
  aislamiento, motivo no filtrado, reintentos, lock con control negativo y suma de costos.
- **Revisor real de dos capas**: análisis estático sin modelo (ruff y bandit fijados, comparación antes/después por
  archivo, regla y conteo) más una revisión con modelo sin herramientas. `4fa19ff`
- **Nodo `documentar`**: el modelo aporta campos acotados y Python arma `documentacion.md`, verificando los endpoints contra
  el OpenAPI de la app desplegada (con respaldo por diff) y las reglas contra `contexto/reglas_negocio.md`. `95e620b`
- **HU-04** «asignar jefe directo» y reglas de negocio 8 a 12 del campo `jefe_id`. `a94e08b`
- **Cobertura de LangGraph**: streaming por nodo con costo acumulado `7433fa3`; `recursion_limit` calculado desde los
  topes, que escala sin traceback `9d56379`; `--historial THREAD_ID` de solo lectura `5042a98`; `RetryPolicy` solo para
  fallos de infraestructura `fd71232`; ciclo de corrección como subgrafo `1ccacc7`.
- **Sandbox de ejecución en Docker** para todo el código que escriben los agentes (`--read-only`, `--cap-drop ALL`,
  `no-new-privileges`, no root, límites, sin entorno del anfitrión; redes `none`, interna para el e2e y front-end en dos
  fases) `682301b`. Una corrida real exige Docker y las imágenes `a6930d7`. Chequeo determinista de
  `docker-compose.yml` antes de `up` (`verificacion/compose_seguro.py`) `682301b`.
- **Prompts de los 8 subagentes** con contexto explícito (rutas con Read, sin `@archivo`), contrato de entrada y salida,
  ejemplo de formato y un bloque de seguridad idéntico en todos, vigilado por `tests/test_agentes.py`. `57d9880`
- Spikes con evidencia: del revisor (no corrido) `ecc066b` y del sandbox (26 ataques fallan, e2e de 48 pruebas dentro del
  sandbox) `9b0bf58`.

### Cambiado
- `registros/` queda bloqueada de forma explícita para todos los agentes, también para escritura, y la auditoría se
  escribe siempre (también con `DEFENSAS=0`) en `registros/auditoria.jsonl` `0e682fc` `d16bde3`.
- El agente de `despliegue` solo puede usar `docker compose up/logs/ps` (antes, `docker` entero); el desarrollador y el
  automatizador ya no ejecutan `pytest` en el anfitrión `682301b`.
- La categoría de revisión «correctitud» pasa a «corrección» `1152166`.
- Documentación: sección «Reto» de `CLAUDE.md` con el sandbox y sus riesgos residuales `a8b1105`, con los prompts
  `af01cb0`; README reescrito para onboarding; bitácora de la fase `826ae95`.

### Corregido
- El revisor ya no puede ser silenciado por el código que revisa: se ignoran `noqa` y `nosec` `44c1fd5`.
- La red del e2e debe **ser** interna, no solo llamarse `fabrica_sandbox`: se inspecciona `.Internal` y el compose no puede
  usar redes `external` ni con nombre explícito `6a9c145`.
- El ejemplo del filtro de seguridad ya no se parece a HU-99 y la evidencia va dentro de `motivo` `9486be0`.

## Fase 1 del reto · Orquestador LangGraph (2026-11-15)

### Añadido
- Spike de `claude -p` desde Python `4584786` y su módulo `flujos/claude.py` `e0b04df`.
- **Grafo orquestador de la fábrica** (`flujos/fabrica.py`): nodos por skill, validación por artefacto, pausas humanas con
  `interrupt`, checkpoints en SQLite y topes en todos los bucles `06f7694`; rutas probadas en modo `--ensayo` `2ca23e9`.
- `/construir` acepta correcciones sobre la versión anterior `bd30631`.
- Sección «Reto» en `CLAUDE.md` `fdd1bd4`.

### Corregido
- `construir` exige que `app/` haya cambiado `29a67fc`; `corregir_codigo` verifica la app antes de redesplegar `495c7c9`.
- El motivo del veredicto vive solo en `registros/` y los veredictos de clase salen de `salida/` `1a73cb6` `c995054`.

### Mantenimiento
- Ignorar los checkpoints SQLite `98c50eb`; `check=False` explícito `d5c3d12`.

## Sesión 4 · Flujo E2E con triage y defensas (2026-11-15)

### Añadido
- **Filtro de seguridad**: contratos `Veredicto` y `Diagnostico` `65b16de`, subagente `filtro-seguridad` `aeb4c34`.
- **`hooks/seguridad.py`** (lectura confinada, secretos, terminal, auditoría) `2890fb4` e interruptor `DEFENSAS` `6d7515b`.
- **Pruebas E2E y redespliegue** `f8ee9ac`; **triage** que enruta al responsable de la corrección `d2d8432`.
- **Guion final `/fabrica`** `a2d3d54`, con prueba de que bloquea HU-99 `f019b1c`; demo con `DEFENSAS=0` `ca7b0fa`.
- Punto de partida de la sesión `0e692c6`, memoria y README `6bd333c`, bitácora, evidencia y comparación con la
  referencia `b9e00ae`.

### Corregido
- Salida de subprocesos y de la consola en UTF-8 en Windows `32f5a84` `a4527b0`.

### Mantenimiento
- Se quitó `.mcp.json` local y los permisos MCP sin servidor `377ef38`; se alinearon dependencias y permisos tras
  comparar con la referencia `f6c2126`.

## Sesiones 1 a 3 · Fábrica M3B (2026-11-14)

### Añadido
- Punto de partida del reto: analista, diseñador de pruebas, arquitecto, desarrollador, despliegue y automatizador como
  subagentes de Claude Code, con `validadores/`, `verificacion/` y la app de gestión de empleados (HU-01 a HU-03)
  `50dcb25`.
