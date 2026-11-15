# Plan HU-01 · Registrar empleado

Estado de app/: ya existen `database.py`, `modelos.py` (Empleado), `main.py` (importa `routers.empleados`, que NO existe), `routers/departamentos.py`, `BuscadorEmpleados.jsx`, `main.jsx` (importa `App.jsx`, que NO existe). Se extiende sin tocar lo existente.

## Modelo de datos
- Tabla `empleados` ya definida en `modelos.py`; no se cambia. `numero_empleado` se asigna en el servidor: `EMP-` + (max(id)+1) con 4 dígitos, dentro de la misma transacción del insert. No se consume si la validación falla (se valida antes).
- `estado="activo"` y `creado_en` los pone el servidor; `correo` se guarda en minúsculas.
- Esquemas Pydantic v2 (`EmpleadoCrear`, `EmpleadoSalida`) en `schemas.py`; los campos de `EmpleadoCrear` son opcionales a nivel Pydantic solo en tipo y longitud (nombre 2-80, puesto 2-60, departamento en lista, fecha_ingreso obligatoria tipo date). Se recortan espacios en nombre y puesto.

## Endpoints
- `POST /api/empleados` -> 201 con el empleado completo (`numero_empleado`, `estado`, `creado_en`, correo en minúsculas). Orden de validación en el router: (1) Pydantic (campo inválido -> 422 por el handler existente `{"detail":"Corrige el campo: X","campo":X}`), (2) dominio: correo sin `@empresa.com` -> 422 "Usa el correo corporativo @empresa.com", (3) fecha > hoy -> 422 "La fecha de ingreso no puede ser futura", (4) correo duplicado (minúsculas, incluye bajas) -> 409 "El correo ya está registrado". Los puntos 2-4 con `HTTPException`, formato `{"detail": ...}`.
- Nota: el correo se valida como `str` en Pydantic (no EmailStr) para que el mensaje de dominio llegue exacto. Un correo vacío o sin formato mínimo da 422 de campo `correo`.
- `GET /api/empleados` -> lista ordenada por id (la usan las pruebas y la tabla).
- `GET /api/departamentos` y `GET /api/salud` ya existen.

## Componentes de React
- `App.jsx`: carga departamentos y empleados, contiene el estado de mensajes y compone el resto.
- `FormularioEmpleado.jsx`: 5 campos (departamento es `<select>`; fecha como `input type="date"`), botón guardar. Envía a `/api/empleados`; con 201 muestra "Empleado registrado con número EMP-000N", limpia el formulario y recarga la tabla; con error muestra `detail` (409/dominio/fecha) o, si hay `campo`, "Corrige el campo: X" en `mensaje-error`. Sin validación HTML5 `required` que bloquee el envío, para que el servidor responda 422.
- `TablaEmpleados.jsx`: filas con número, nombre, correo, puesto, departamento, fecha, estado ("Activo"/"Baja").
- `BuscadorEmpleados.jsx` existe; no se usa en esta HU.

## data-testid
`empleado-nombre`, `empleado-correo`, `empleado-puesto`, `empleado-departamento`, `empleado-fecha-ingreso`, `empleado-guardar`, `mensaje-exito`, `mensaje-error`, `tabla-empleados`, `fila-empleado-{id}`, `numero-empleado-{id}`, `estado-empleado-{id}`. El correo de la fila se muestra en una celda dentro de la fila.

## Archivos a crear o modificar
- Crear `app/backend/schemas.py`, `app/backend/routers/empleados.py`.
- Crear `app/frontend/src/App.jsx`, `componentes/FormularioEmpleado.jsx`, `componentes/TablaEmpleados.jsx`.
- Verificar (modificar solo si falta) `app/backend/requirements.txt` (fastapi, uvicorn, sqlalchemy, pydantic), `app/frontend/vite.config.js` (proxy `/api` -> 8000, puerto 5173), `index.html` con `#root`.
- Sin cambios: `main.py`, `modelos.py`, `database.py`, `departamentos.py`.

## Preguntas abiertas asumidas
Fechas antiguas se aceptan; el número no se consume al fallar; se recortan espacios; las bajas conservan el correo reservado.
