#!/usr/bin/env bash
set -euo pipefail

image="${1:?usage: check_sandbox_no_secrets.sh IMAGE}"
environment_json="$(docker image inspect --format '{{json .Config.Env}}' "${image}")"

for forbidden in \
  ANTHROPIC_API_KEY \
  OPENAI_API_KEY \
  LANGSMITH_API_KEY \
  LANGCHAIN_API_KEY \
  GITHUB_TOKEN \
  GH_TOKEN \
  DAYTONA_API_KEY \
  RUNLOOP_API_KEY \
  E2B_API_KEY
do
  if jq -e --arg prefix "${forbidden}=" \
    'any(.[]; startswith($prefix))' <<<"${environment_json}" >/dev/null
  then
    echo "credential variable embedded in image configuration: ${forbidden}" >&2
    exit 1
  fi
done

echo "sandbox image configuration contains no forbidden credential variables"
