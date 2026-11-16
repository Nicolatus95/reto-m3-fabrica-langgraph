Estado real de app/: backend/main.py, database.py, modelos.py, schemas.py, esquemas.py, servicio_empleados.py, routers/empleados.py, routers/departamentos.py; frontend/src/App.jsx, api.js, componentes/TablaEmpleados.jsx, FormularioEdicion.jsx (más la lista de archivos vista en el Glob).
Nota: la API en uso es routers/empleados.py + schemas.py. esquemas.py y servicio_empleados.py no los importa el router (código muerto): NO se tocan, para no tener dos fuentes de verdad.
## Modelo de datos
- Empleado (backend/modelos.py): se AGREGA `jefe_id: Mapped[int | None]` con ForeignKey("empleados.id"), nullable. Se conservan todas las columnas actuales.
- La BD existente (datos/empleados.db) ya tiene la tabla: create_all NO agrega columnas. Se AGREGA en main.py, tras create_all, una migración mínima: si PRAGMA table_info(empleados) no trae jefe_id, ejecutar `ALTER TABLE empleados ADD COLUMN jefe_id INTEGER REFERENCES empleados(id)`.
- schemas.py: EmpleadoEditar pasa a `puesto`/`departamento` opcionales (None = sin cambio; un valor presente se valida igual que hoy) y se AGREGA `jefe_id: int | None = None`; se distingue «no enviado» de «null» con `model_fields_set`. EmpleadoSalida AGREGA `jefe_id: int | None` y `jefe_nombre: str | None`. Se conservan EmpleadoCrear, BajaEntrada y el resto.
## Endpoints (se conservan GET/POST/baja actuales)
- PUT /api/empleados/{id} (EXTENDER el existente) con jefe_id. Orden de validación: 404 si no existe; 409 si el empleado está en baja (regla 6); si jefe_id viene y no es null: 422 «Un empleado no puede ser su propio jefe» (jefe_id == id); 422 «El jefe indicado no existe»; 409 «Un empleado dado de baja no puede ser jefe»; 422 «La asignación crearía un ciclo en la línea de reporte» (subir por la cadena de jefes desde el jefe propuesto; si aparece `id`, es ciclo; cubre directo e indirecto). jefe_id null quita el jefe → 200. Reasignar el mismo jefe → 200 sin cambios. Ante cualquier error no se modifica nada (validar antes del commit).
- POST /api/empleados/{id}/baja (EXTENDER): al dar de baja, `UPDATE` de los empleados con jefe_id == id a jefe_id NULL en la misma transacción (regla 12).
- GET /api/empleados y GET /api/empleados/{id}: la salida incluye jefe_id y jefe_nombre (en la lista, un dict id→nombre de TODOS los empleados, para que el nombre salga aunque el buscador filtre al jefe).
## Componentes de React
- api.js: sin función nueva; editarEmpleado ya envía el cuerpo JSON (se le pasa jefe_id).
- App.jsx (MODIFICAR): estado `candidatos` = listarEmpleados() sin filtros, recargado junto con cargarEmpleados; se pasa a FormularioEdicion filtrado a estado «activo».
- FormularioEdicion.jsx (MODIFICAR): AGREGA `<select data-testid="empleado-jefe">` con opción vacía «Sin jefe» y los candidatos activos excepto el propio empleado; valor inicial empleado.jefe_id; onGuardar(id, {puesto, departamento, jefe_id: valor ? Number(valor) : null}). Errores de la API salen por el mensaje-error existente.
- TablaEmpleados.jsx (MODIFICAR): columna «Jefe» con celda `jefe-empleado-{id}` que muestra jefe_nombre o queda vacía si no hay (decisión sobre la pregunta abierta; el selector no ofrece al propio empleado ni a dados de baja, por eso CP-08 solo se cubre por API).
## data-testid
- Se conservan todos los de las convenciones. Nuevos (hay que añadirlos a contexto/convenciones_app.md por quien lo mantenga): `empleado-jefe` (selector de jefe), `jefe-empleado-{id}` (celda de jefe por fila).
## Archivos a crear o modificar
- Modificar: backend/modelos.py, backend/main.py (migración), backend/schemas.py, backend/routers/empleados.py, frontend/src/App.jsx, componentes/FormularioEdicion.jsx, componentes/TablaEmpleados.jsx.
- No crear archivos. Sin cambios: esquemas.py, servicio_empleados.py, database.py, api.js, requirements.txt.
- Riesgo: hacer opcionales puesto/departamento en el PUT cambia el 422 actual por campo ausente; los casos API de HU-04 envían solo jefe_id.
