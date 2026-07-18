#!/bin/sh
set -eu

usage() {
  echo "usage: xlsliberator-build-farm-client [--endpoint URL] health" >&2
}

endpoint="${XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT:-}"
if [ "${1:-}" = "--endpoint" ]; then
  endpoint="${2:-}"
  shift 2
fi

if [ "${1:-}" != "health" ] || [ -z "${endpoint}" ]; then
  usage
  exit 64
fi

case "${endpoint}" in
  http://*|https://*) ;;
  *) echo "build-farm endpoint must use http or https" >&2; exit 64 ;;
esac

curl --fail --silent --show-error \
  --connect-timeout 5 \
  --max-time "${XLSLIBERATOR_BUILD_FARM_CLIENT_TIMEOUT_SECONDS:-30}" \
  "${endpoint%/}/health"
