FROM python:3.9-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update -y && apt-get install -qq --force-yes ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /code
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

CMD ["python3", "-m", "src.bot"]
