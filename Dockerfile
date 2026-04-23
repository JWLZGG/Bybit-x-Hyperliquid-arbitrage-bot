FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system bot && adduser --system --ingroup bot bot

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY scripts ./scripts
COPY tests ./tests
COPY README.md ./
COPY .env.example ./

RUN mkdir -p /app/logs /app/data && chown -R bot:bot /app

USER bot

EXPOSE 8080

CMD ["python", "-m", "bot.main"]
