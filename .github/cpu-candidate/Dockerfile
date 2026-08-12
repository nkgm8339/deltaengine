FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ARG CANDIDATE_REVISION

LABEL org.opencontainers.image.source="https://github.com/nkgm8339/deltaengine"
LABEL org.opencontainers.image.revision="$CANDIDATE_REVISION"
LABEL deltaengine.production_base_image="sha256:a27e727ebb5b8648ccd5dc1ebaf9f0543c3e9a9f2a61b24519d4df51c2dc51c1"
LABEL deltaengine.cpu_validation_run="31605823961"
LABEL deltaengine.big_trades_activation="disabled"

WORKDIR /app

COPY runtime/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements.lock.txt \
    && rm /tmp/requirements.lock.txt

COPY runtime/requirements.txt /app/requirements.txt
COPY runtime/src /app/src
COPY runtime/webapp /app/webapp

CMD ["uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "8080"]
