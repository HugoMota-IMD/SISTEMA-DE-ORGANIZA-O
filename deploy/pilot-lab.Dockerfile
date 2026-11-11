FROM python:3.14.6-slim-trixie AS python
FROM postgres:18.6
COPY --from=python /usr/local /usr/local
RUN apt-get update && apt-get install -y --no-install-recommends pgbouncer age openssl libsqlite3-0 libbz2-1.0 liblzma5 libffi8 libexpat1 libreadline8 && ldconfig && rm -rf /var/lib/apt/lists/*
WORKDIR /work
COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt PyYAML
COPY --chown=postgres:postgres . /work
RUN mkdir -p /work/test-results && chown -R postgres:postgres /work
USER postgres
ENTRYPOINT ["python", "tools/verify_pilot_lab.py"]
