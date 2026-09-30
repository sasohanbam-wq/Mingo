FROM python:3.12-slim
WORKDIR /app
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY server/toss_bridge.py /app/toss_bridge.py
ENV PORT=8000
CMD ["sh","-c","uvicorn toss_bridge:app --host 0.0.0.0 --port ${PORT}"]
