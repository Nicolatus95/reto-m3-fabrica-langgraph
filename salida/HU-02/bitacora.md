# Bitácora HU-02 · Consultar el directorio

**Estado final: LISTA** (CP-13 y CP-14 pasan desde que HU-03 agregó la ruta de baja; ver la nota al final)

1. Analista: 7 escenarios en criterios.feature.
2. Compuerta de criterios: válido.
3. Preguntas abiertas: 7 preguntas mostradas; la persona dijo que continuara (asunciones del analista y del arquitecto aceptadas).
4. Diseñador de pruebas: 14 casos (7 api, 7 e2e); casos_prueba.json válido.
5. Plan: el primer plan se rechazó (1 rechazo) porque describía un app/ sin los archivos de HU-01 y habría sobrescrito su POST y su frontend. El segundo plan, que extiende solo GET /api/empleados con `buscar` y `departamento`, fue aprobado por la persona.
6. Desarrollador: modificó routers/empleados.py (GET con filtros), App.jsx y TablaEmpleados.jsx. No creó el archivo de pruebas del plan, porque las pruebas son del automatizador.
7. Verificación app: OK (backend 200; frontend compila).
8. Despliegue y automatización en paralelo: ambos terminaron.
9. Unión: verificación despliegue OK (3 URL en 200); verificación pruebas OK (34 recolectados).
   Ejecutadas contra la app: 32 pasan y 2 fallan; los 20 tests de HU-01 siguen pasando.
   - Fallan CP-13 (api) y CP-14 (e2e): el empleado de baja sigue en el directorio. Su preparación llama a `POST /api/empleados/{id}/baja`, que devuelve 404 porque la aplicación aún no tiene esa ruta (`servicio_empleados.dar_de_baja` existe pero no está conectada a un router).
   - Es una dependencia de HU-03, no un defecto de los tests ni de la búsqueda y el filtro. No se relanzó al automatizador, porque no habría arreglado nada.
   - Acción pendiente: volver a ejecutar `python -m pytest app/tests` tras HU-03. Si la ruta de baja de HU-03 no es `POST /api/empleados/{id}/baja` con `fecha_baja`, ajustar una línea en cada test de HU-02 mediante el automatizador.

Actualización tras HU-03: la suite completa (HU-01, HU-02 y HU-03) se ejecutó contra la app desplegada y pasaron los 48 tests, CP-13 y CP-14 de HU-02 incluidos.

URLs: app http://localhost:8080 · API http://localhost:8000/docs
