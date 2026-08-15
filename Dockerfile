ARG PYTHON_IMAGE=python:3.12.13-slim-trixie
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/rocm-host/libexec/amdsmi_cli:/opt/rocm-host/bin:${PATH} \
    PYTHONPATH=/app:/opt/rocm-host/libexec/amdsmi_cli:/opt/rocm-host/share/amd_smi \
    ROCM_PATH=/opt/rocm-host

RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl libdrm-amdgpu1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 portal \
    && useradd --uid 10001 --gid portal --create-home --shell /usr/sbin/nologin portal

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY --chown=portal:portal backend/ /app/
COPY --chown=portal:portal container/amd-smi /usr/local/bin/amd-smi

RUN chmod 0755 /usr/local/bin/amd-smi \
    && mkdir /data \
    && chown portal:portal /data

USER portal

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=5 \
    CMD curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/health >/dev/null || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
