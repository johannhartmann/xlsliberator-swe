#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
versions_file="${repository_root}/docker/xlsliberator-sandbox/versions.env"

# shellcheck source=/dev/null
source "${versions_file}"

image="${XLSLIBERATOR_SANDBOX_IMAGE_OVERRIDE:-${XLSLIBERATOR_SANDBOX_IMAGE}}"
office_image="${XLSLIBERATOR_OFFICE_IMAGE_OVERRIDE:-${XLSLIBERATOR_OFFICE_IMAGE}}"
xlsliberator_context="${XLSLIBERATOR_BUILD_CONTEXT:-https://github.com/johannhartmann/xlsliberator.git#${XLSLIBERATOR_SOURCE_COMMIT}}"
open_swe_commit="$(git -C "${repository_root}" rev-parse HEAD)"

if ! git -C "${repository_root}" diff --quiet \
  || ! git -C "${repository_root}" diff --cached --quiet
then
  echo "tracked Open SWE files must be committed before an identified image build" >&2
  exit 65
fi

if [ -d "${xlsliberator_context}/.git" ]; then
  context_commit="$(git -C "${xlsliberator_context}" rev-parse HEAD)"
  if [ "${context_commit}" != "${XLSLIBERATOR_SOURCE_COMMIT}" ]; then
    echo "XLSLiberator context is ${context_commit}; expected ${XLSLIBERATOR_SOURCE_COMMIT}" >&2
    exit 65
  fi
  if [ -n "$(git -C "${xlsliberator_context}" status --porcelain)" ]; then
    echo "local XLSLiberator build context must be clean" >&2
    exit 65
  fi
fi

docker build \
  --tag "${office_image}" \
  --file docker/office/libreoffice/Dockerfile \
  "${xlsliberator_context}"

docker build \
  --tag "${image}" \
  --build-context "xlsliberator=${xlsliberator_context}" \
  --build-arg "XLSLIBERATOR_OFFICE_IMAGE=${office_image}" \
  --build-arg "OPEN_SWE_SOURCE_COMMIT=${open_swe_commit}" \
  --build-arg "XLSLIBERATOR_SOURCE_COMMIT=${XLSLIBERATOR_SOURCE_COMMIT}" \
  --build-arg "XLSLIBERATOR_SANDBOX_VERSION=${XLSLIBERATOR_SANDBOX_VERSION}" \
  --build-arg "XLSLIBERATOR_SANDBOX_IMAGE=${image}" \
  --build-arg "LIBREOFFICE_BUILD=${XLSLIBERATOR_LIBREOFFICE_VERSION}" \
  --file "${repository_root}/docker/xlsliberator-sandbox/Dockerfile" \
  "${repository_root}"

docker image inspect \
  --format 'image={{index .Config.Labels "org.xlsliberator.sandbox.image"}} id={{.Id}} open_swe={{index .Config.Labels "org.opencontainers.image.revision"}} xlsliberator={{index .Config.Labels "org.xlsliberator.source.revision"}} libreoffice={{index .Config.Labels "org.xlsliberator.libreoffice.version"}}' \
  "${image}"
