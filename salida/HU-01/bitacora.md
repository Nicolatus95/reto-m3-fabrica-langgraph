# Bitácora HU-01 · Registrar empleado

**Estado final: LISTA**

1. Analista: 10 escenarios en criterios.feature.
2. Compuerta de criterios: válido.
3. Preguntas abiertas: 4 preguntas mostradas; la persona dijo que continuara (asunciones del analista aceptadas).
4. Diseñador de pruebas: 20 casos (10 api, 10 e2e); casos_prueba.json válido.
5. Plan: aprobado por la persona a la primera (sin rechazos).
6. Desarrollador: backend (schemas.py, routers/empleados.py) y frontend (App.jsx, FormularioEmpleado.jsx, TablaEmpleados.jsx). Reescribió archivos que ya existían de una corrida anterior.
7. Verificación app: OK (backend responde 200 en 8010; frontend compila).
8. Despliegue y automatización en paralelo: ambos terminaron.
9. Unión: verificación despliegue OK (3 URL en 200); verificación pruebas OK (20 recolectados).
   Ejecutadas contra la app: 19 pasaron y 1 falló (CP-06 e2e usaba el testid `buscar-empleados` de un componente que esta HU no usa).
   Se relanzó UNA vez al automatizador con el log; tras la corrección, 20 de 20 pasan y la verificación pruebas sigue en OK.

Pendiente fuera de la fábrica: advertencia de pytest 10 sobre una fixture `base_url` de sesión definida como método de instancia. No está en app/tests/; su origen no se identificó.

URLs: app http://localhost:8080 · API http://localhost:8000/docs
