#!/bin/sh
set -eu

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

for command_name in \
  bash cargo convert curl docker file gh git go java jq node open-swe-python \
  python3.11 python3.12 rg shellcheck soffice unzip uv wget xvfb-run yarn zip
do
  require_command "${command_name}"
done

test "$(soffice --version | awk '{print $2}')" = "26.2.4.2"
test "$(dpkg-query -W -f='${Version}' libobasis26.2-python-script-provider)" = "26.2.4.2-2"

PYTHONPATH=/opt/libreoffice26.2/program:/opt/xlsliberator-source/src \
  /opt/libreoffice26.2/program/python -c \
  'import pyuno, uno; assert uno.__file__.startswith("/opt/libreoffice26.2/program/"); assert pyuno.__file__.startswith("/opt/libreoffice26.2/program/")'

python3.11 --version
python3.12 --version
open-swe-python -c "import deepagents, langgraph, langsmith"
python -c "import msoffcrypto, oletools, openpyxl, pyxlsb, xlsliberator"

xlsprobe --help >/dev/null
odstool --help >/dev/null
migration-check --help >/dev/null
xlsliberator-build-farm-client --help >/dev/null 2>&1 || test "$?" = "64"

xvfb-run -a sh -c 'xdpyinfo >/dev/null'
convert -size 16x16 xc:white /tmp/xlsliberator-smoke.png
test -s /tmp/xlsliberator-smoke.png

xlsliberator-sandbox-identity | jq -e \
  '.status == "PASSED" and .image.libreoffice_build == "26.2.4.2"' >/dev/null
test -s /workspace/.xlsliberator/sandbox-identity.json
test -f /opt/xlsliberator-source/skills/workbook-forensics/SKILL.md
test -f /opt/xlsliberator-source/skills/vba-to-python-uno/SKILL.md
test -f /opt/xlsliberator-source/skills/userform-to-uno/SKILL.md
test -z "$(find /opt/xlsliberator-source/skills -type l -print -quit)"
test "$(du -sk /opt/xlsliberator-source/skills | cut -f1)" -le 4096

/opt/xlsliberator-venv/bin/python /opt/xlsliberator-sandbox/mcp_smoke.py

echo "XLSLiberator sandbox smoke: PASSED"
