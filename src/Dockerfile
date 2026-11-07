# Imagen base liviana de Python 3.12
FROM python:3.12-slim

# Evitar escritura de bytecode y buffering de stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación
COPY app/ ./src/app/

# Exponer el puerto del servidor HTTP
EXPOSE 8000

# Ejecutar Uvicorn escuchando en 0.0.0.0
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
