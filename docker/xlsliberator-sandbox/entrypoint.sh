#!/bin/sh
set -eu

umask 077
workspace="${XLSLIBERATOR_JOB_WORKSPACE:-/workspace}"
identity_dir="${workspace}/.xlsliberator"

if [ ! -d "${workspace}" ] || [ ! -w "${workspace}" ]; then
  echo "writable job workspace required: ${workspace}" >&2
  exit 73
fi

mkdir -p "${identity_dir}"
temporary="${identity_dir}/sandbox-identity.json.tmp"
xlsliberator-sandbox-identity > "${temporary}"
mv "${temporary}" "${identity_dir}/sandbox-identity.json"

exec "$@"
