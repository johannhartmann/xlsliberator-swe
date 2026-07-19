ARG XLSLIBERATOR_OFFICE_IMAGE=xlsliberator-libreoffice:26.2.4.2
FROM ${XLSLIBERATOR_OFFICE_IMAGE}

ARG TARGETARCH
ARG OPEN_SWE_SOURCE_COMMIT=unknown
ARG XLSLIBERATOR_SOURCE_COMMIT
ARG XLSLIBERATOR_SANDBOX_VERSION=2026.07.0
ARG XLSLIBERATOR_SANDBOX_IMAGE=ghcr.io/johannhartmann/xlsliberator-swe-sandbox:2026.07.0
ARG LIBREOFFICE_BUILD=26.2.4.2
ARG DOCKER_CLI_VERSION=5:29.1.5-1~debian.12~bookworm
ARG UV_VERSION=0.9.26
ARG NODE_VERSION=22.22.0
ARG YARN_VERSION=4.12.0
ARG GH_VERSION=2.83.1
ARG SFW_BINARY_VERSION=1.13.1
ARG GO_VERSION=1.23.5

LABEL org.opencontainers.image.title="XLSLiberator Open SWE sandbox" \
      org.opencontainers.image.version="${XLSLIBERATOR_SANDBOX_VERSION}" \
      org.opencontainers.image.revision="${OPEN_SWE_SOURCE_COMMIT}" \
      org.opencontainers.image.source="https://github.com/johannhartmann/xlsliberator-swe" \
      org.xlsliberator.source.revision="${XLSLIBERATOR_SOURCE_COMMIT}" \
      org.xlsliberator.libreoffice.version="${LIBREOFFICE_BUILD}" \
      org.xlsliberator.sandbox.image="${XLSLIBERATOR_SANDBOX_IMAGE}"

USER 0

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/sandbox \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_LINK_MODE=copy \
    XLSLIBERATOR_APPLICATION_CONTAINER=1 \
    XLSLIBERATOR_CHECKOUT_PATH=/workspace/xlsliberator \
    XLSLIBERATOR_ARTIFACT_ROOT=/workspace/artifacts/workbooks \
    XLSLIBERATOR_SANDBOX_CPU_COUNT=2 \
    XLSLIBERATOR_SANDBOX_MEMORY_BYTES=8321499136 \
    XLSLIBERATOR_SANDBOX_DISK_BYTES=34359738368 \
    XLSLIBERATOR_SANDBOX_PIDS_LIMIT=1024 \
    XLSLIBERATOR_SANDBOX_COMMAND_TIMEOUT_SECONDS=1800 \
    XLSLIBERATOR_SANDBOX_IDLE_TTL_SECONDS=7200 \
    XLSLIBERATOR_SANDBOX_DELETE_AFTER_STOP_SECONDS=86400

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       bash build-essential ca-certificates cargo chromium curl default-jre-headless \
       file git gnupg imagemagick jq libffi-dev libssl-dev make openssh-client \
       pkg-config procps ripgrep shellcheck tini unzip wget xauth xdg-utils \
       xfonts-base x11-utils xvfb xz-utils zip \
    && rm -rf /var/lib/apt/lists/*

RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
       -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "docker-ce-cli=${DOCKER_CLI_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
      amd64) node_arch="x64"; node_sha256="9aa8e9d2298ab68c600bd6fb86a6c13bce11a4eca1ba9b39d79fa021755d7c37" ;; \
      arm64) node_arch="arm64"; node_sha256="1bf1eb9ee63ffc4e5d324c0b9b62cf4a289f44332dfef9607cea1a0d9596ba6f" ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    archive="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/${archive}" -o "/tmp/${archive}"; \
    echo "${node_sha256}  /tmp/${archive}" | sha256sum -c -; \
    tar -xJf "/tmp/${archive}" -C /usr/local --strip-components=1; \
    rm "/tmp/${archive}"; \
    corepack enable; \
    corepack prepare "yarn@${YARN_VERSION}" --activate

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
      amd64) sfw_arch="x86_64"; sfw_sha256="4dc46b626a7c5b81c0b54e1984ee53be5a628dbfb2f55ab14e9b04c8a134db6a" ;; \
      arm64) sfw_arch="arm64"; sfw_sha256="f87bbbca2192fca9740f9bdb115e7cfaa22e957a8f5234d5f97fce1383aa1d66" ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    binary="sfw-free-linux-${sfw_arch}"; \
    curl -fsSL \
      "https://github.com/SocketDev/sfw-free/releases/download/v${SFW_BINARY_VERSION}/${binary}" \
      -o "/tmp/${binary}"; \
    echo "${sfw_sha256}  /tmp/${binary}" | sha256sum -c -; \
    install -m 0755 "/tmp/${binary}" /usr/local/bin/sfw; \
    rm "/tmp/${binary}"; \
    sfw --version

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
      amd64) gh_arch="amd64"; gh_sha256="835afbb0404889c5595929117eccb2681547c387f6a711b50b08288436de7b22" ;; \
      arm64) gh_arch="arm64"; gh_sha256="cc21469d749a88fdd53f9242dc3005bd4f8fe4dcd2a2d2a9adf1681c97827ef8" ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    package="gh_${GH_VERSION}_linux_${gh_arch}.deb"; \
    curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/${package}" \
      -o "/tmp/${package}"; \
    echo "${gh_sha256}  /tmp/${package}" | sha256sum -c -; \
    apt-get update; \
    apt-get install -y --no-install-recommends "/tmp/${package}"; \
    rm -rf "/tmp/${package}" /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
      amd64) uv_arch="x86_64-unknown-linux-gnu"; uv_sha256="30ccbf0a66dc8727a02b0e245c583ee970bdafecf3a443c1686e1b30ec4939e8" ;; \
      arm64) uv_arch="aarch64-unknown-linux-gnu"; uv_sha256="f71040c59798f79c44c08a7a1c1af7de95a8d334ea924b47b67ad6b9632be270" ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    archive="uv-${uv_arch}.tar.gz"; \
    curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${archive}" \
      -o "/tmp/${archive}"; \
    echo "${uv_sha256}  /tmp/${archive}" | sha256sum -c -; \
    tar -xzf "/tmp/${archive}" -C /tmp; \
    install -m 0755 "/tmp/uv-${uv_arch}/uv" /usr/local/bin/uv; \
    install -m 0755 "/tmp/uv-${uv_arch}/uvx" /usr/local/bin/uvx; \
    rm -rf "/tmp/${archive}" "/tmp/uv-${uv_arch}"; \
    uv python install 3.11 3.12; \
    ln -s "$(uv python find 3.11)" /usr/local/bin/python3.11; \
    ln -s "$(uv python find 3.12)" /usr/local/bin/python3.12

RUN set -eux; \
    arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
    case "${arch}" in \
      amd64) go_arch="amd64"; go_sha256="cbcad4a6482107c7c7926df1608106c189417163428200ce357695cc7e01d091" ;; \
      arm64) go_arch="arm64"; go_sha256="47c84d332123883653b70da2db7dd57d2a865921ba4724efcdf56b5da7021db0" ;; \
      *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
    esac; \
    archive="go${GO_VERSION}.linux-${go_arch}.tar.gz"; \
    curl -fsSL "https://go.dev/dl/${archive}" -o "/tmp/${archive}"; \
    echo "${go_sha256}  /tmp/${archive}" | sha256sum -c -; \
    tar -xzf "/tmp/${archive}" -C /usr/local; \
    rm "/tmp/${archive}"

COPY pyproject.toml uv.lock README.md /opt/open-swe/
COPY scripts/create_sandbox_snapshot.py /opt/open-swe/scripts/create_sandbox_snapshot.py
COPY agent/xlsliberator/showcase.py /opt/xlsliberator-showcase/showcase.py

RUN UV_PROJECT_ENVIRONMENT=/opt/open-swe-venv \
    uv sync \
      --project /opt/open-swe \
      --locked \
      --extra dev \
      --no-install-project \
      --python /usr/local/bin/python3.12

COPY --from=xlsliberator pyproject.toml README.md /opt/xlsliberator-source/
COPY --from=xlsliberator src /opt/xlsliberator-source/src
COPY --from=xlsliberator rules /opt/xlsliberator-source/rules
COPY --from=xlsliberator skills /opt/xlsliberator-source/skills
COPY docker/xlsliberator-sandbox/xlsliberator-env/pyproject.toml \
     docker/xlsliberator-sandbox/xlsliberator-env/uv.lock \
     /opt/xlsliberator-environment/

RUN test -n "${XLSLIBERATOR_SOURCE_COMMIT}" \
    && UV_PROJECT_ENVIRONMENT=/opt/xlsliberator-venv \
       uv sync \
         --project /opt/xlsliberator-environment \
         --locked \
         --python /usr/local/bin/python3.12 \
         --no-install-project \
    && uv pip install \
         --python /opt/xlsliberator-venv/bin/python \
         --no-deps \
         --editable /opt/xlsliberator-source \
    && chmod -R a-w /opt/xlsliberator-source

COPY docker/xlsliberator-sandbox/entrypoint.sh /usr/local/bin/xlsliberator-sandbox-entrypoint
COPY docker/xlsliberator-sandbox/open-swe-python.sh /usr/local/bin/open-swe-python
COPY docker/xlsliberator-sandbox/identity.sh /usr/local/bin/xlsliberator-sandbox-identity
COPY docker/xlsliberator-sandbox/smoke.sh /usr/local/bin/xlsliberator-sandbox-smoke
COPY docker/xlsliberator-sandbox/mcp_smoke.py /opt/xlsliberator-sandbox/mcp_smoke.py
COPY docker/xlsliberator-sandbox/build_farm_client.sh /usr/local/bin/xlsliberator-build-farm-client

RUN chmod 0555 \
      /usr/local/bin/xlsliberator-sandbox-entrypoint \
      /usr/local/bin/open-swe-python \
      /usr/local/bin/xlsliberator-sandbox-identity \
      /usr/local/bin/xlsliberator-sandbox-smoke \
      /usr/local/bin/xlsliberator-build-farm-client \
      /opt/xlsliberator-sandbox/mcp_smoke.py \
      /opt/xlsliberator-showcase/showcase.py \
      /opt/open-swe/scripts/create_sandbox_snapshot.py \
    && ln -s /opt/libreoffice26.2/program/soffice /usr/local/bin/soffice \
    && mkdir -p /etc/xlsliberator-sandbox /workspace /home/sandbox /tmp/home \
    && jq -n \
      --arg image "${XLSLIBERATOR_SANDBOX_IMAGE}" \
      --arg version "${XLSLIBERATOR_SANDBOX_VERSION}" \
      --arg open_swe_commit "${OPEN_SWE_SOURCE_COMMIT}" \
      --arg xlsliberator_commit "${XLSLIBERATOR_SOURCE_COMMIT}" \
      --arg libreoffice_build "${LIBREOFFICE_BUILD}" \
      '{schema_version: 1, status: "PASSED", image: {name: $image, version: $version, open_swe_commit: $open_swe_commit, xlsliberator_commit: $xlsliberator_commit, libreoffice_build: $libreoffice_build}}' \
      > /etc/xlsliberator-sandbox/identity.json \
    && { \
      python3.11 --version; \
      python3.12 --version; \
      /opt/libreoffice26.2/program/python --version; \
      soffice --version; \
      uv --version; \
      node --version; \
      yarn --version; \
      gh --version | head -1; \
      git --version; \
      /usr/local/go/bin/go version; \
      cargo --version; \
      java -version 2>&1 | head -1; \
      convert -version | head -1; \
      /opt/xlsliberator-venv/bin/python -c 'import importlib.metadata as m; print("xlsliberator", m.version("xlsliberator")); print("openpyxl", m.version("openpyxl")); print("oletools", m.version("oletools")); print("pyxlsb", m.version("pyxlsb")); print("msoffcrypto-tool", m.version("msoffcrypto-tool")); print("pytest", m.version("pytest")); print("ruff", m.version("ruff")); print("mypy", m.version("mypy"))'; \
    } > /etc/xlsliberator-sandbox/versions.txt \
    && test "$(/opt/libreoffice26.2/program/soffice --version | awk '{print $2}')" = "${LIBREOFFICE_BUILD}" \
    && test "$(dpkg-query -W -f='${Version}' libobasis26.2-python-script-provider)" = "${LIBREOFFICE_BUILD}-2" \
    && PYTHONPATH=/opt/libreoffice26.2/program \
       /opt/libreoffice26.2/program/python -c 'import pyuno, uno; assert uno.__file__.startswith("/opt/libreoffice26.2/program/"); assert pyuno.__file__.startswith("/opt/libreoffice26.2/program/")' \
    && if ! getent group 10001 >/dev/null; then groupadd --gid 10001 sandbox; fi \
    && if ! getent passwd 10001 >/dev/null; then \
         useradd --uid 10001 --gid 10001 --home-dir /home/sandbox --shell /bin/bash sandbox; \
       fi \
    && chown -R 10001:10001 /workspace /home/sandbox /tmp/home \
    && chmod 0555 /etc/xlsliberator-sandbox/identity.json \
    && chmod 0444 /etc/xlsliberator-sandbox/versions.txt

ENV PATH=/opt/xlsliberator-venv/bin:/opt/open-swe-venv/bin:/usr/local/go/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONPATH=/opt/xlsliberator-source/src \
    STAGEHAND_LOCAL_CHROME_PATH=/usr/bin/chromium

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/xlsliberator-sandbox-entrypoint"]
CMD ["bash"]
