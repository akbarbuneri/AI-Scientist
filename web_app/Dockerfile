FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt /app/
COPY web_app/requirements.txt /app/web_app/
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -r web_app/requirements.txt
COPY . /app
EXPOSE 8000
CMD ["uvicorn", "web_app.app:app", "--host", "0.0.0.0", "--port", "8000"]
