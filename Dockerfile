FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn -w 2 --threads 4 --timeout 60 -b 0.0.0.0:${PORT:-8000} app:app"]
