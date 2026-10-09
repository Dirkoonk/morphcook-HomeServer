FROM python:3.13-alpine
WORKDIR /app
COPY server.py .
ENV MORPHCOOK_DB=/data/morphcook.db
VOLUME /data
CMD ["python", "-u", "server.py"]
