# Plan HU-02: Consultar el directorio (buscar y filtrar)

Cambios por comentarios: el plan anterior partía de un app/ vacío. Ahora extiende lo existente de HU-01 (no duplica POST ni esquemas) y no debe romper sus 20 tests.

Estado actual: `main.py` monta `routers/empleados.py`, que usa `schemas.py` (EmpleadoCrear/EmpleadoSalida). `esquemas.py` y `servicio_empleados.py` (con `listar_empleados(q, departamento)`) no están conectados al router; no se tocan ni se importan (evita mezclar dos juegos de esquemas).
En el front, `BuscadorEmpleados.jsx`, `FiltroDepartamento.jsx` y `api.listarEmpleados({buscar, departamento})` ya existen pero `App.jsx` no los usa.

## Modelo de datos
Sin cambios: tabla `Empleado` (estado, fecha_baja, departamento ya existen). Sin migraciones.

## Endpoints
- Solo se modifica `GET /api/empleados`; el POST queda intacto.
- Parámetros opcionales: `buscar` (texto) y `departamento` (texto exacto). Sin parámetros devuelve todos, igual que hoy (compatibilidad HU-01).
- `buscar`: coincidencia parcial, sin distinguir mayúsculas, sobre nombre y correo (asunción de las preguntas abiertas); se hace con `casefold()` en Python porque `lower()` de SQLite falla con acentos.
- `departamento`: filtro con `==` en SQL; se combina con `buscar` (AND). Un departamento sin empleados da `[]` con 200.
- Orden por `id`; incluye empleados en baja (con `fecha_baja`). Respuesta: `list[EmpleadoSalida]` de `schemas.py`.

## Componentes de React
- `App.jsx`: estados `buscar` y `departamento`; `useEffect` llama a `listarEmpleados({buscar, departamento})` ante cada cambio (con un pequeño debounce de 250 ms o ninguno); conserva `cargarEmpleados` como `alRegistrar` del formulario. Renderiza `BuscadorEmpleados` y `FiltroDepartamento` (ya existen) sobre la tabla.
- `TablaEmpleados.jsx`: columna Puesto ya está; si `empleados` está vacío, no se renderizan filas y se muestra `<p data-testid="sin-resultados">No se encontraron empleados</p>`. Mantiene `tabla-empleados` visible.
- `api.js` y los demás componentes: sin cambios.

## data-testid
Existentes: `tabla-empleados`, `fila-empleado-{id}`, `numero-empleado-{id}`, `estado-empleado-{id}` (Activo/Baja), `buscar-empleados`, `filtro-departamento`. Nuevo en uso: `sin-resultados`.

## Archivos a crear o modificar
- Modificar `app/backend/routers/empleados.py`: solo la función `listar_empleados` (agregar `Query` opcionales `buscar`, `departamento`).
- Modificar `app/frontend/src/App.jsx`: estado, carga filtrada, montar buscador y filtro.
- Modificar `app/frontend/src/componentes/TablaEmpleados.jsx`: mensaje `sin-resultados`.
- Pruebas: agregar `app/backend/tests/test_listado.py` (CP-01, 03, 05, 07, 09, 11, 13) sin editar los tests de HU-01 (si no existe la carpeta de tests, ubicarla donde estén los de HU-01).
- Verificar al final: los 20 tests de HU-01 pasan, `GET /api/salud` responde y `npm run build` sin errores.
