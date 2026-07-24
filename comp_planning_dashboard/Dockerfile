# Build from this directory:
#   docker build -t comp-planning-dashboard .
#   docker run -p 8000:8000 -v $(pwd)/data:/app/data comp-planning-dashboard
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . /app
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
