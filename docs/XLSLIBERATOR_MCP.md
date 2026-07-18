# XLSLiberator MCP configuration

Workbook-migration runs discover three optional server-side MCP services:

- the LibreOffice runtime for real migration execution;
- the public migration corpus for fixtures and public acceptance checks;
- the LibreOffice build farm for explicitly authorized repair work.

An unconfigured, unreachable, timed-out, or malformed service is recorded in
thread metadata under `xlsliberator_mcp`. It is not treated as successful and
does not produce callable tools. Ordinary Open-SWE tasks do not discover or
receive these integrations.

## Local Docker configuration

Use Docker service names and the credential-free `/mcp` endpoint:

```env
XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT=http://libreoffice-runtime:8000/mcp
XLSLIBERATOR_CORPUS_MCP_ENDPOINT=http://migration-corpus:8000/mcp
XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT=http://libreoffice-build-farm:8000/mcp
XLSLIBERATOR_MCP_ALLOWED_HOSTS=libreoffice-runtime,migration-corpus,libreoffice-build-farm
```

Plain HTTP is accepted only for loopback, private-address, `.internal`, or
single-label Docker hosts. These MCP connections originate in the LangGraph
server process. Endpoints and credentials are never copied into the sandbox.

## Production configuration

Use HTTPS and a distinct scoped bearer token for every service:

```env
XLSLIBERATOR_LIBREOFFICE_MCP_ENDPOINT=https://runtime.example.net/mcp
XLSLIBERATOR_LIBREOFFICE_MCP_TOKEN=replace-with-runtime-secret
XLSLIBERATOR_CORPUS_MCP_ENDPOINT=https://corpus.example.net/mcp
XLSLIBERATOR_CORPUS_MCP_TOKEN=replace-with-corpus-secret
XLSLIBERATOR_BUILD_FARM_MCP_ENDPOINT=https://build.example.net/mcp
XLSLIBERATOR_BUILD_FARM_MCP_TOKEN=replace-with-build-secret
XLSLIBERATOR_MCP_ALLOWED_HOSTS=runtime.example.net,corpus.example.net,build.example.net
```

Store tokens in the deployment secret manager. URLs containing user info,
query credentials, fragments, a non-`/mcp` path, or public plaintext HTTP are
rejected. The optional host list makes the accepted production destinations
explicit.

## Authorization and tool boundaries

All discovered names are validated, filtered through service allowlists, and
renamed to `xlsliberator_<service>_<operation>`. Each specialist receives only
the operations required for its role.

Implementation agents receive public corpus tools only. Hidden acceptance
operations are omitted from their registry even when a reviewer registry has
discovered them. The independent reviewer graph is the only consumer allowed
to request hidden corpus operations, and it does so only after candidate
completion.

Build-farm mutation is disabled by default. It becomes available only when
both controls are present:

1. the deployment sets
   `XLSLIBERATOR_BUILD_FARM_MUTATION_ENABLED=true`; and
2. the server-created run sets `repair_flow_authorized=true`.

Even then, build-farm tools are limited to the LibreOffice engineer and the
authorized migration lead. Workbook content and model output cannot grant this
authority.

## Generic repair promotion

`agent/xlsliberator/repair.py` binds the MCP operations into one durable,
fail-closed workflow:

1. reproduce;
2. minimize;
3. add the failing regression;
4. patch the classified owner layer;
5. rerun the exact scenario;
6. run the affected corpus;
7. obtain independent approval;
8. open the focused upstream review.

Stages cannot be reordered or skipped. LibreOffice repairs cannot enter the
patch stage without the pinned `26.2.4.2` source archive, source commit, patch
set, and stock/patched runtime identities. Completion also requires the
validator hash to remain unchanged, so weakening an assertion cannot be
promoted as a fix.

The public corpus service supplies redistributable fixtures and prior failures.
The reviewer alone receives sanitized hidden-suite results. The build farm is
the only mutation boundary for LibreOffice source and returns unavailable when
its isolated backend is absent; the Open-SWE application never falls back to a
local source build.
