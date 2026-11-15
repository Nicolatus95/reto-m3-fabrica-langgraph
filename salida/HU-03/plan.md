# Plan HU-03 · Editar y dar de baja a un empleado

Estado real de app/: leí backend/main.py, modelos.py, schemas.py, esquemas.py, servicio_empleados.py, routers/empleados.py; frontend/src/App.jsx, api.js, componentes/TablaEmpleados.jsx, FormularioEdicion.jsx, FormularioBaja.jsx (existen también FormularioEmpleado, BuscadorEmpleados y FiltroDepartamento, sin tocar).
Conclusión: el código previo ya cubre casi toda la HU; el plan es verificar y hacer ajustes mínimos, sin reescribir nada. No hay comentarios previos de revisión.

## Modelo de datos
- Sin cambios. Se conserva la tabla `empleados` (modelos.py) con `estado` ("activo"/"baja") y `fecha_baja` (Date, nulo).
- Se conservan `schemas.py` (EmpleadoEditar con puesto 2-60 con strip y departamento Literal; BajaEntrada; EmpleadoSalida), que es el que usa el router.

## Endpoints (ya existentes en routers/empleados.py, se conservan)
- `GET /api/empleados/{id}`: 200 o 404 "Empleado no encontrado".
- `PUT /api/empleados/{id}` (puesto, departamento): 200; 409 "No se puede editar a un empleado dado de baja"; 422 con `detail` "Corrige el campo: puesto|departamento" (lo genera el manejador de main.py). Número y correo no se tocan; los campos extra se ignoran.
- `POST /api/empleados/{id}/baja` (fecha_baja): 200 con estado "baja"; 422 "Corrige el campo: fecha_baja" si es anterior al ingreso o falta/inválida; 409 si ya está en baja. El empleado no se borra y sigue en `GET /api/empleados`.
- Decisiones sobre las preguntas abiertas: la fecha de baja la captura RR. HH.; se permite fecha futura; 404 para id inexistente; baja repetida responde 409 con el mismo mensaje.

## Componentes de React (ya existentes, se conservan)
- `App.jsx`: maneja `editando`, `dandoBaja` y `mensaje` (éxito/error), y recarga la lista tras guardar.
- `FormularioEdicion.jsx`: puesto + select de departamentos (solo ofrece los válidos).
- `FormularioBaja.jsx`: input de fecha y confirmar.
- `TablaEmpleados.jsx`: muestra "Activo"/"Baja"; el botón de baja se oculta si el empleado está en baja.
- `api.js`: `editarEmpleado`, `darDeBajaEmpleado` (el mensaje del `detail` llega a `mensaje-error`).

## data-testid (todos ya presentes)
`editar-empleado-{id}`, `baja-empleado-{id}`, `fila-empleado-{id}`, `numero-empleado-{id}`, `estado-empleado-{id}`, `tabla-empleados`, `empleado-puesto`, `empleado-departamento`, `empleado-guardar`, `empleado-fecha-baja`, `confirmar-baja`, `mensaje-exito`, `mensaje-error`.

## Archivos a crear o modificar
Crear: ninguno.
Modificar (opcional, bajo riesgo):
1. `app/backend/routers/empleados.py`: comprobar que `PUT` valida el cuerpo antes de aplicar cambios y que un error no deja cambios a medias (hoy es correcto: solo se asigna tras validar). Sin cambio funcional previsto.
2. `app/backend/servicio_empleados.py` y `app/backend/esquemas.py`: duplicados sin uso (el router usa `schemas.py`). No se editan en esta HU; solo se deja constancia para que no se importen por error y se produzcan mensajes distintos ("fecha de baja" vs "fecha_baja").
Verificación del desarrollador: ejecutar los 14 casos CP-01..CP-14 y confirmar que el 422 menciona el nombre exacto del campo (`puesto`, `departamento`, `fecha_baja`) y que `npm run build` termina sin errores.
