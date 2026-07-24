// APS validation-gate runner — steps 2–5 of the six-step gate in
// docs/APS_SDK_BUILDOUT.md. Step 1 (app creation, credentials into the env
// store) and step 6 (Design Automation / employer-hub decisions) are human
// gates and are not automated here.
//
// Usage:
//   node src/gate.mjs            # run steps 2..5 in order, stop on failure
//   node src/gate.mjs --step 3   # run a single step
//
// Credentials come ONLY from the environment: APS_CLIENT_ID, APS_CLIENT_SECRET.
// Secrets are never printed and never written to evidence files.
// Evidence lands in evidence/gate-<runstamp>.json (gitignored — hub, project,
// and file names count as private data and must not reach the public repo).

import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { AuthenticationClient, Scopes } from "@aps_sdk/authentication";
import { DataManagementClient } from "@aps_sdk/data-management";
import { ModelDerivativeClient } from "@aps_sdk/model-derivative";
import { OssClient } from "@aps_sdk/oss";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MODEL = join(ROOT, "testdata", "aps_test_model.dxf");
const READ_SCOPES = [Scopes.DataRead, Scopes.ViewablesRead];
// Step 4 needs a sandbox bucket + upload + translate job; still no ACC/hub writes.
const STEP4_SCOPES = [...READ_SCOPES, Scopes.DataWrite, Scopes.DataCreate, Scopes.BucketCreate, Scopes.BucketRead];

function credentials() {
  const clientId = process.env.APS_CLIENT_ID;
  const clientSecret = process.env.APS_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    console.error(
      "GATE BLOCKED (fail closed): APS_CLIENT_ID / APS_CLIENT_SECRET are not set.\n" +
      "Step 1 of the gate is a human step: create the APS app at aps.autodesk.com\n" +
      "and place the credentials in the environment store. Never paste them into chat."
    );
    process.exit(2);
  }
  return { clientId, clientSecret };
}

const evidence = { started: new Date().toISOString(), steps: [] };

function record(step, name, ok, detail) {
  evidence.steps.push({ step, name, ok, detail, at: new Date().toISOString() });
  console.log(`[gate ${step}] ${ok ? "PASS" : "FAIL"} — ${name}`);
  if (!ok) console.error(detail);
}

async function token(scopes) {
  const { clientId, clientSecret } = credentials();
  const auth = new AuthenticationClient();
  const t = await auth.getTwoLeggedToken(clientId, clientSecret, scopes);
  return t.access_token;
}

// Step 2 — two-legged auth via @aps_sdk/authentication.
async function step2() {
  const accessToken = await token(READ_SCOPES);
  const ok = typeof accessToken === "string" && accessToken.length > 20;
  record(2, "two-legged token obtained", ok, {
    token_sha256_prefix: createHash("sha256").update(accessToken).digest("hex").slice(0, 12),
    scopes: READ_SCOPES,
  });
  return ok;
}

// Step 3 — Data Management: enumerate hubs/projects/top folders (read-only).
// With a fresh personal app this legitimately returns zero hubs until an ACC
// hub grants the app access; zero hubs with a clean 200 still proves the pipe.
async function step3() {
  const accessToken = await token(READ_SCOPES);
  const dm = new DataManagementClient();
  const hubs = await dm.getHubs({ accessToken });
  const summary = [];
  for (const hub of hubs.data ?? []) {
    const projects = await dm.getHubProjects(hub.id, { accessToken });
    summary.push({
      hub: hub.attributes?.name,
      hubId: hub.id,
      projects: (projects.data ?? []).map((p) => p.attributes?.name),
    });
  }
  record(3, "data-management hub/project enumeration", true, {
    hubCount: (hubs.data ?? []).length,
    summary,
    note: "zero hubs is expected for a fresh app with no ACC account linked",
  });
  return true;
}

// Step 4 — OSS upload of the synthetic test model + Model Derivative translate.
async function step4() {
  const accessToken = await token(STEP4_SCOPES);
  const modelPath = process.env.APS_TEST_MODEL ?? DEFAULT_MODEL;
  const bucketKey = process.env.APS_TEST_BUCKET ?? `eld-aps-gate-${createHash("sha256").update(credentials().clientId).digest("hex").slice(0, 10)}`;
  const oss = new OssClient();

  try {
    await oss.createBucket("US", { bucketKey, policyKey: "transient" }, { accessToken });
  } catch (e) {
    if (e?.axiosError?.response?.status !== 409) throw e; // 409 = already exists, fine
  }
  const objectKey = basename(modelPath);
  await oss.uploadObject(bucketKey, objectKey, readFileSync(modelPath), { accessToken });
  const details = await oss.getObjectDetails(bucketKey, objectKey, { accessToken });
  const urn = Buffer.from(details.objectId).toString("base64url");

  const md = new ModelDerivativeClient();
  await md.startJob({ input: { urn }, output: { formats: [{ type: "svf2", views: ["2d", "3d"] }] } }, { accessToken });

  let status = "inprogress", manifest;
  for (let i = 0; i < 60 && (status === "inprogress" || status === "pending"); i++) {
    await new Promise((r) => setTimeout(r, 10_000));
    manifest = await md.getManifest(urn, { accessToken });
    status = manifest.status;
    if (status === "success" || status === "failed" || status === "timeout") break;
  }
  const ok = status === "success";
  record(4, "oss upload + model-derivative translate", ok, {
    bucketKey, objectKey, objectSize: details.size, urn, translateStatus: status,
  });
  evidence.urn = urn;
  return ok;
}

// Step 5 — element properties via Model Derivative, spot-checked against the
// generator's own validated ground truth (layer names from make_test_model.py).
async function step5() {
  const accessToken = await token(READ_SCOPES);
  const urn = evidence.urn ?? process.env.APS_TEST_URN;
  if (!urn) {
    record(5, "properties extraction", false, "no URN — run step 4 first or set APS_TEST_URN");
    return false;
  }
  const md = new ModelDerivativeClient();
  const views = await md.getModelViews(urn, { accessToken });
  const guid = views.data?.metadata?.[0]?.guid;
  const props = await md.getAllProperties(urn, guid, { accessToken });
  const text = JSON.stringify(props).slice(0, 200_000);
  const expectedLayers = ["V-PARCEL", "V-BLDG-PAD", "V-EASEMENT", "V-ANNO"];
  const found = expectedLayers.filter((l) => text.includes(l));
  const ok = found.length >= 3; // annotation layer naming can vary by extractor
  record(5, "properties extraction spot-check vs generator ground truth", ok, {
    viewGuid: guid, expectedLayers, foundLayers: found,
  });
  return ok;
}

const STEPS = { 2: step2, 3: step3, 4: step4, 5: step5 };

async function main() {
  const arg = process.argv.indexOf("--step");
  const selected = arg > -1 ? [Number(process.argv[arg + 1])] : [2, 3, 4, 5];
  credentials(); // fail closed before any network call
  let allOk = true;
  for (const s of selected) {
    try {
      const ok = await STEPS[s]();
      if (!ok) { allOk = false; break; }
    } catch (e) {
      record(s, "unhandled error", false, String(e?.axiosError?.response?.data ? JSON.stringify(e.axiosError.response.data) : e));
      allOk = false;
      break;
    }
  }
  evidence.finished = new Date().toISOString();
  evidence.result = allOk ? "PASS" : "FAIL";
  const dir = join(ROOT, "evidence");
  mkdirSync(dir, { recursive: true });
  const out = join(dir, `gate-${evidence.started.replace(/[:.]/g, "-")}.json`);
  writeFileSync(out, JSON.stringify(evidence, null, 2));
  console.log(`evidence: ${out}\nresult: ${evidence.result}`);
  process.exit(allOk ? 0 : 1);
}

main();
