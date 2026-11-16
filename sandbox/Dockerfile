# Imagen del sandbox (nuestra: ningún agente la escribe ni la puede escribir; ver hooks/roles.py).
# Ejecuta pruebas (pytest, pytest-playwright, httpx) y verifica el backend SIN red.
# Las versiones están FIJADAS: las del .venv. El backend solo puede usar estas dependencias; si su requirements.txt pide
# otra, sandbox/verificar_backend.py lo dice (instalar paquetes arbitrarios sería ejecutar código arbitrario).
# Se construye una vez:  python -m verificacion imagen_sandbox   →  fabrica-sandbox:1
FROM mcr.microsoft.com/playwright/python:v1.65.2-noble

RUN pip install --no-cache-dir --break-system-packages \
    pytest==9.2.0 pytest-playwright==0.10.0 httpx==0.28.1 \
    fastapi==0.163.0 uvicorn==0.54.0 sqlalchemy==2.1.8 pydantic==2.14.3

COPY verificar_backend.py /opt/verificar_backend.py

USER pwuser
WORKDIR /work
