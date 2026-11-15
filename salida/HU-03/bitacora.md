# Bitácora HU-03 · Editar y dar de baja empleados

**Estado final: LISTA**

1. Analista: 7 escenarios en criterios.feature.
2. Compuerta de criterios: válido.
3. Preguntas abiertas: 6 preguntas mostradas; la persona dijo que continuara (asunciones del analista y del arquitecto aceptadas).
4. Diseñador de pruebas: 14 casos (7 api, 7 e2e); casos_prueba.json válido.
5. Plan: el primer plan se rechazó (1 rechazo) porque partía de un app/ sin los archivos de HU-01 y HU-02 y habría sobrescrito schemas.py, TablaEmpleados.jsx y App.jsx. El segundo plan, que solo agrega PUT /api/empleados/{id}, POST /api/empleados/{id}/baja y GET /api/empleados/{id}, fue aprobado por la persona.
6. Desarrollador: agregó EmpleadoEditar y BajaEntrada a schemas.py, tres rutas a routers/empleados.py, FormularioEdicion.jsx y extendió TablaEmpleados.jsx y App.jsx. No escribió pruebas.
7. Verificación app: OK (backend 200; frontend compila).
8. Despliegue y automatización en paralelo: ambos terminaron.
9. Unión: verificación despliegue OK (3 URL en 200); verificación pruebas OK (48 recolectados).
   Ejecutadas contra la app: 48 de 48 pasan (HU-01: 20, HU-02: 14, HU-03: 14).

Observaciones:
- CP-04 (e2e) cubre menos de lo descrito: la pantalla solo ofrece departamentos válidos, así que comprueba que «Marketing» no está en la lista y que la fila no cambia, no el `mensaje-error`. El rechazo con 422 queda cubierto por CP-03 (api).
- Mientras hay una edición o baja abierta, App.jsx oculta el formulario de registro para no duplicar los data-testid.
- Sigue pendiente la advertencia de pytest 10 sobre una fixture `base_url` de sesión definida como método de instancia. No está en app/tests/; su origen no se identificó.

URLs: app http://localhost:8080 · API http://localhost:8000/docs
