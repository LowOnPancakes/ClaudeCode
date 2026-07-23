# Build from the org_chart_converter/ directory (one level up from this file):
#   docker build -f webapp/Dockerfile -t org-chart-webapp .
#   docker run -p 8000:8000 org-chart-webapp
FROM python:3.11-slim
WORKDIR /app
COPY webapp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY org_chart_converter.py /app/org_chart_converter.py
COPY webapp/ /app/webapp/
WORKDIR /app/webapp
EXPOSE 8000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
