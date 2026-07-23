# Civil 3D MCP Build-Out Guide — barbosaihan/civil3d-mcp

Workstation build and validation guide for the Civil 3D MCP connector, registered as candidate infrastructure in `docs/AGENT_REGISTRY.md`. All commands and requirements below were extracted verbatim from the upstream repository docs on 2026-07-23; re-verify against the repo before executing, since it is a fast-moving single-author project with no releases.

Upstream: https://github.com/barbosaihan/civil3d-mcp

## What it is

An MCP server that lets an AI assistant write and execute C# code inside a running Civil 3D session. Architecture: AI assistant (Claude) ↔ stdio ↔ TypeScript MCP server (3 meta-tools) ↔ TCP/JSON-RPC on port 8080 ↔ Civil 3D plugin hosting a Roslyn compiler with full Civil 3D API access.

The three meta-tools:

| Tool | Behavior | Safety |
| --- | --- | --- |
| `civil3d_query` | Execute C# read-only, nothing committed | No side effects |
| `civil3d_execute` | Execute C# with write access, transaction committed | Modifies the drawing |
| `civil3d_skills` | Browse/search/read vetted C# code templates (`list`, `search`, `get`) | Metadata only |

Executed scripts get globals `Document`, `CivilDoc`, `Database`, `Transaction`, `Editor`, with all Civil 3D namespaces auto-imported. The Roslyn sandbox blocks process execution, file deletion, network requests, registry access, and dynamic assembly loading; all Civil 3D API operations are allowed.

## Prerequisites

- Windows workstation with Civil 3D installed. The upstream docs do not state a supported Civil 3D version; the only signals are a `C:\Program Files\Autodesk\AutoCAD 2025\` copy path and a `net8.0-windows` build target matching Civil 3D 2025's .NET 8 runtime. Treat 2025 as the tested target; any other release is unverified.
- .NET 8 SDK (plugin build target is `net8.0-windows`).
- Node.js for the MCP server. No required Node version is documented; the dev dependencies suggest Node 22-era. Install current LTS.

## Build steps

1. **Clone the repo** on the Civil 3D workstation.

2. **Build the MCP server**:

   ```
   npm install && npm run build
   ```

3. **Copy Civil 3D managed DLLs** into `C_References/` (from the Civil 3D installation directory, typically `C:\Program Files\Autodesk\AutoCAD 2025\`):
   - `accoremgd.dll` (AutoCAD Core Managed)
   - `AcDbMgd.dll` (AutoCAD Database Managed)
   - `acmgd.dll` (AutoCAD Managed)
   - `AecBaseMgd.dll` (AEC Base Managed)
   - `AeccDbMgd.dll` (Civil 3D Database Managed)

   These DLLs are proprietary Autodesk files and must never be committed to version control (the repo's `.gitignore` already excludes them). A different install path can be pointed at via the overridable `Civil3DReferencesPath` MSBuild property instead of editing the project file.

4. **Build the plugin**:

   ```
   cd plugin/Civil3dMcpPlugin
   dotnet build
   ```

5. **Load in Civil 3D**: run `NETLOAD` and select `Civil3dMcpPlugin.dll`, then run `C3DMCPSTATUS` to verify the plugin is running.

6. **Register the MCP server** in the Claude config (the upstream README gives one generic block; place it in the Claude Desktop or Claude Code MCP config as appropriate):

   ```json
   { "mcpServers": { "civil3d": { "command": "node", "args": ["/path/to/civil3d-mcp/build/index.js"] } } }
   ```

7. **Environment variables** (defaults): `CIVIL3D_HOST` = `localhost`, `CIVIL3D_PORT` = `8080`, `CIVIL3D_COMMAND_TIMEOUT` = `120000` ms, `LOG_LEVEL` = `info`.

## Validation gate (registry requirement)

The registry entry stays `candidate` until every step below has recorded evidence:

1. `C3DMCPSTATUS` reports running, and the MCP server appears in Claude's tool list.
2. `civil3d_skills` with `action: "list"` returns the template library (categories: surfaces, alignments, points, geometry, drawing, workflows).
3. **Read-only proof on copies**: `civil3d_query` operations on copies of real project DWGs — list surfaces, drawing metadata, a surface elevation or cut/fill volume via the documented skill templates — with results spot-checked against Civil 3D's own reports.
4. Sandbox probe: confirm a blocked operation (e.g., a network request) is actually rejected.
5. Only after 1–4: a single `civil3d_execute` write on a scratch copy, verified by readback, then rolled back by discarding the copy.

## Governance boundaries

- Write access (`civil3d_execute`) falls under the one-designated-writer rule; Agent 007 holds the writer lease until the connector is validated.
- Production DWGs require explicit task-level instruction; all development and validation happens on copies.
- The executed-code blocklist (process execution, file deletion, network, registry, dynamic loading) is recorded in the registry entry and re-verified at each weekly audit.
- Firm-specific skills (earthwork quantity reports for submittals, grading checks, station/offset extraction for LFUCG/KYTC packages) are authored as `.skill.md` files per the format in `docs/ABSORBED_PATTERNS.md` §6 and reviewed like any other capability.

## Rollback

Remove the `civil3d` entry from the Claude MCP config and unload/delete the plugin DLL. The connector holds no persistent state; drawings touched during validation are copies and are discarded.
