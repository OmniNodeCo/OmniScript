FROM python:3.12-slim
WORKDIR /opt/omniscript
COPY . .
RUN python -m pip install --no-cache-dir .
WORKDIR /workspace
ENTRYPOINT ["omni"]
CMD ["--help"]
