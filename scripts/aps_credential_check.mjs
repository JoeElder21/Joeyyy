#!/usr/bin/env node
/**
 * APS readiness check — run on any machine with APS credentials to complete
 * steps 1-3 of the validation gate in docs/APS_SDK_BUILDOUT.md.
 *
 * Usage:
 *   export APS_CLIENT_ID=...      # from aps.autodesk.com (never commit)
 *   export APS_CLIENT_SECRET=...
 *   npm install @aps_sdk/autodesk-sdkmanager @aps_sdk/authentication @aps_sdk/data-management
 *   node scripts/aps_credential_check.mjs
 *
 * Read-only: requests data:read scope only, lists hubs/projects on the
 * sandbox account, prints a JSON report, and stores nothing.
 */

import { SdkManagerBuilder } from "@aps_sdk/autodesk-sdkmanager";
import { AuthenticationClient, Scopes } from "@aps_sdk/authentication";
import { DataManagementClient } from "@aps_sdk/data-management";

const clientId = process.env.APS_CLIENT_ID;
const clientSecret = process.env.APS_CLIENT_SECRET;
if (!clientId || !clientSecret) {
  console.error(JSON.stringify({
    ok: false,
    error: "APS_CLIENT_ID / APS_CLIENT_SECRET not set in the environment",
    note: "Credentials live only in the runtime env store; never in chat or the repo.",
  }, null, 2));
  process.exit(1);
}

const sdk = SdkManagerBuilder.create().build();
const auth = new AuthenticationClient(sdk);
const dm = new DataManagementClient(sdk);

try {
  const token = await auth.getTwoLeggedToken(clientId, clientSecret, [Scopes.DataRead]);
  const hubs = await dm.getHubs({ accessToken: token.access_token });
  const names = (hubs.data ?? []).map((hub) => hub.attributes?.name ?? hub.id);
  console.log(JSON.stringify({
    ok: true,
    gate_steps_completed: [2, 3],
    hubs_visible: names.length,
    hubs: names,
    next: "Steps 4-5 per docs/APS_SDK_BUILDOUT.md (OSS upload + model-derivative translate on a sandbox model).",
  }, null, 2));
} catch (error) {
  console.error(JSON.stringify({
    ok: false,
    error: String(error?.message ?? error),
    note: "Two-legged auth or hub listing failed; verify the APS app and scopes.",
  }, null, 2));
  process.exit(1);
}
