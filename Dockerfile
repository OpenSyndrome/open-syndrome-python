FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.1.1

COPY . /app

RUN poetry config virtualenvs.create false && poetry install

ENTRYPOINT ["uv", "run", "osi"]
