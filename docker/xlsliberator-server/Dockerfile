ARG XLSLIBERATOR_SANDBOX_IMAGE
FROM ${XLSLIBERATOR_SANDBOX_IMAGE}

USER 0:0

COPY . /opt/open-swe-app

RUN touch /opt/open-swe-app/.env \
    && chmod 0600 /opt/open-swe-app/.env \
    && mkdir -p /var/lib/open-swe/xlsliberator-mcp-bridge

ENV HOME=/root \
    PYTHONPATH=/opt/open-swe-app \
    XLSLIBERATOR_APPLICATION_CONTAINER=1

WORKDIR /opt/open-swe-app
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/open-swe-venv/bin/langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser", "--allow-blocking", "--no-reload"]
