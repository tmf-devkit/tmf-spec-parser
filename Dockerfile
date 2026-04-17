FROM python:3.12-slim

WORKDIR /app

# Install with optional YAML support
COPY pyproject.toml README.md LICENSE ./
COPY tmf_spec_parser ./tmf_spec_parser

RUN pip install --no-cache-dir ".[yaml]"

# Cache directory inside container — mount a volume to persist across runs:
#   docker run -v $(pwd)/cache:/root/.tmf-spec-parser/cache mchavan23/tmf-spec-parser generate
ENV TMF_CACHE_DIR=/root/.tmf-spec-parser/cache

ENTRYPOINT ["tmf-spec-parser"]
CMD ["--help"]
