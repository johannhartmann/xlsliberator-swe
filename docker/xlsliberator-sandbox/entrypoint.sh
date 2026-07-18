#!/bin/sh
set -eu

umask 077
workspace="${XLSLIBERATOR_JOB_WORKSPACE:-/workspace}"
identity_dir="${workspace}/.xlsliberator"
checkout="${XLSLIBERATOR_CHECKOUT_PATH:-${workspace}/xlsliberator}"

if [ ! -d "${workspace}" ] || [ ! -w "${workspace}" ]; then
  echo "writable job workspace required: ${workspace}" >&2
  exit 73
fi
if [ "${checkout}" != "${workspace}/xlsliberator" ]; then
  echo "checkout must be confined to the job workspace: ${checkout}" >&2
  exit 64
fi
if [ ! -e "${checkout}" ]; then
  cp -R /opt/xlsliberator-source "${checkout}"
  chmod -R u+rwX "${checkout}"
fi

mkdir -p "${identity_dir}"
temporary="${identity_dir}/sandbox-identity.json.tmp"
xlsliberator-sandbox-identity > "${temporary}"
mv "${temporary}" "${identity_dir}/sandbox-identity.json"

exec "$@"
