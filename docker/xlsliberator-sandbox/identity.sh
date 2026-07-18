#!/bin/sh
set -eu

identity_file=/etc/xlsliberator-sandbox/identity.json
test -r "${identity_file}"

jq \
  --arg digest "${XLSLIBERATOR_SANDBOX_IMAGE_DIGEST:-}" \
  --arg snapshot_id "${DEFAULT_SANDBOX_SNAPSHOT_ID:-}" \
  '. + {
    runtime: {
      image_digest: (if $digest == "" then null else $digest end),
      snapshot_id: (if $snapshot_id == "" then null else $snapshot_id end)
    }
  }' \
  "${identity_file}"
