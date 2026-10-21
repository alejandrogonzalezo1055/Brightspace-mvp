FROM python:3.11-slim
WORKDIR /srv/mock-brightspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY admin.py .
ENV DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8800
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8800", "--proxy-headers"]
