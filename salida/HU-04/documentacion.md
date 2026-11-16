# Documentación · HU-04

> Generada por un modelo a partir del código que cambió. El código solo verifica las rutas de los endpoints y los números de regla; lo demás es la lectura del modelo.

## Resumen

HU-04 agrega a cada empleado un jefe directo (jefe\_id) y muestra el nombre del jefe en el directorio. Al editar un empleado se asigna o se quita su jefe, con validaciones de autojefatura, existencia, baja y ciclos en la línea de reporte. Al dar de baja a un jefe, sus subordinados quedan sin jefe en la misma transacción. Incluye una migración mínima que agrega la columna jefe\_id a una tabla existente.

## Endpoints

Verificados contra el OpenAPI de la app desplegada.

| Método | Ruta | Descripción |
| --- | --- | --- |
| GET | /api/empleados | Lista empleados; cada uno incluye jefe\_id y jefe\_nombre, con el nombre tomado de todos los empleados. |
| GET | /api/empleados/{id} | Devuelve un empleado con jefe\_id y jefe\_nombre. |
| PUT | /api/empleados/{id} | Edita puesto, departamento y jefe. Si se envía jefe\_id no nulo valida que no sea el mismo empleado, que exista, que no esté dado de baja y que no cree ciclo. Enviar jefe\_id nulo quita el jefe. Un empleado dado de baja responde 409. |
| POST | /api/empleados/{id}/baja | Da de baja al empleado y deja sin jefe a sus subordinados en la misma transacción. |
| POST | /api/empleados | Registra un empleado; la respuesta incluye jefe\_id y jefe\_nombre, que quedan vacíos al registrar. |

## Reglas cubiertas

- Regla 6: Un empleado dado de baja no se puede editar. El intento responde 409 con el mensaje «No se puede editar a un empleado dado de baja».
- Regla 8: Un empleado no puede ser su propio jefe. El intento responde 422 con el mensaje «Un empleado no puede ser su propio jefe».
- Regla 9: El jefe debe existir. Si no, responde 422 con el mensaje «El jefe indicado no existe».
- Regla 10: Un empleado dado de baja no puede ser jefe de nadie. El intento responde 409 con el mensaje «Un empleado dado de baja no puede ser jefe».
- Regla 11: No se permiten ciclos en la línea de reporte. El intento responde 422 con el mensaje «La asignación crearía un ciclo en la línea de reporte».
- Regla 12: Al dar de baja a un empleado que es jefe, sus subordinados quedan sin jefe.

## Cómo probar

1. Abrir el directorio y comprobar que aparece la columna Jefe y que el formulario de edición muestra el campo Jefe.
2. Editar un empleado activo, elegir un jefe activo y guardar; la fila debe mostrar el nombre del jefe.
3. Enviar por la API jefe\_id igual al id del propio empleado; debe responder 422 con el mensaje de autojefatura.
4. Asignar como jefe a un empleado que ya reporta al editado (ciclo); debe responder 422 con el mensaje de ciclo.
5. Dar de baja a un jefe y comprobar que sus subordinados quedan con jefe vacío.
6. Revisar app/tests/api/test\_hu\_04.py y app/tests/e2e/test\_hu\_04\_e2e.py, ejecutados con la verificación en sandbox.

## Limitaciones

- Quitar el jefe (jefe\_id nulo) no pasa por las validaciones de jefe; según el código solo se valida cuando se envía un jefe no nulo.
- Asignar jefe a un empleado dado de baja responde 409 por la regla de edición (regla 6) antes de validar al jefe; la historia no lo menciona (no verificado).
- La columna Jefe muestra vacío cuando no hay jefe; la historia no lo define (no verificado).
- Volver a asignar el mismo jefe que ya tiene se acepta según el código; no está confirmado con pruebas (no verificado).
- El selector de jefe en pantalla solo lista empleados activos y excluye al propio empleado; la validación final ocurre en el backend al guardar.
