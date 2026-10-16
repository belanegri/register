FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN SECRET_KEY=build-only-not-for-runtime DATABASE_URL=postgresql://build:build@localhost/build DEBUG=False STORAGE_MODE=local python manage.py collectstatic --noinput
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
CMD ["gunicorn", "pontocar.wsgi:application", "--config", "gunicorn.conf.py"]
