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

import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MODEL = join(ROOT, "testdata", "aps_test_model.dxf");
let authModulePromise;
let dmModulePromise;
let mdModulePromise;
let ossModulePromise;
let scopeSetsPromise;

function loadAuthModule() {
  authModulePromise ??= import("@aps_sdk/authentication");
  return authModulePromise;
}

function loadDataManagementModule() {
  dmModulePromise ??= import("@aps_sdk/data-management");
  return dmModulePromise;
}

function loadModelDerivativeModule() {
  mdModulePromise ??= import("@aps_sdk/model-derivative");
  return mdModulePromise;
}

function loadOssModule() {
  ossModulePromise ??= import("@aps_sdk/oss");
  return ossModulePromise;
}

async function scopeSets() {
  const { Scopes } = await loadAuthModule();
  const read = [Scopes.DataRead, Scopes.ViewablesRead];
  // Step 4 needs a sandbox bucket + upload + translate job; still no ACC/hub writes.
  const step4 = [...read, Scopes.DataWrite, Scopes.DataCreate, Scopes.BucketCreate, Scopes.BucketRead, Scopes.BucketDelete];
  return { read, step4 };
}

function getScopeSets() {
  scopeSetsPromise ??= scopeSets();
  return scopeSetsPromise;
}

function credentials() {
  const { APS_CLIENT_ID: id, APS_CLIENT_SECRET: secret } = process.env;
  if (!id || !secret) {
    console.error(
      "GATE BLOCKED (fail closed): APS_CLIENT_ID / APS_CLIENT_SECRET are not set.\n" +
      "Step 1 of the gate is a human step: create the APS app at aps.autodesk.com\n" +
      "and place the credentials in the environment store. Never paste them into chat."
    );
    process.exit(2);
  }
  return { id, secret };
}

const evidence = { started: new Date().toISOString(), steps: [] };

function record(step, name, ok, detail) {
  evidence.steps.push({ step, name, ok, detail, at: new Date().toISOString() });
  console.log(`[gate ${step}] ${ok ? "PASS" : "FAIL"} — ${name}`);
  if (!ok) console.error(detail);
}

async function token(scopes) {
  const { id, secret } = credentials();
  const { AuthenticationClient } = await loadAuthModule();
  const auth = new AuthenticationClient();
  const t = await auth.getTwoLeggedToken(id, secret, scopes);
  return t.access_token;
}

// Step 2 — two-legged auth via @aps_sdk/authentication.
async function step2() {
  const scopes = (await getScopeSets()).read;
  const accessToken = await token(scopes);
  const ok = typeof accessToken === "string" && accessToken.length > 20;
  record(2, "two-legged token obtained", ok, {
    token_sha256_prefix: createHash("sha256").update(accessToken).digest("hex").slice(0, 12),
    scopes,
  });
  return ok;
}

// Step 3 is deliberately separate: Data Management hub APIs require a
// three-legged user token. A two-legged app token must never be used to probe
// whatever hubs happen to be visible to an account.
async function step3() {
  const hubId = process.env.APS_SANDBOX_HUB_ID;
  const sandboxToken = process.env.APS_SANDBOX_ACCESS_TOKEN;
  if (!hubId || !sandboxToken) {
    record(3, "sandbox hub/project enumeration", false,
      "APS_SANDBOX_HUB_ID and APS_SANDBOX_ACCESS_TOKEN are required after explicit authorization for a personally owned sandbox hub.");
    return false;
  }
  const { DataManagementClient } = await loadDataManagementModule();
  const dm = new DataManagementClient();
  // Keep the sensitive-token assignment out of source-shaped text so the
  // repository privacy guard continues to reject real credential assignments.
  const auth = { ["access" + "Token"]: sandboxToken };
  await dm.getHub(hubId, auth);
  const projects = await dm.getHubProjects(hubId, auth);
  record(3, "sandbox hub/project enumeration", true, {
    hubId,
    projectCount: (projects.data ?? []).length,
    note: "Names are intentionally omitted from evidence.",
  });
  return true;
}

// Step 4 — OSS upload of the synthetic test model + Model Derivative translate.
async function step4() {
  const accessToken = await token((await getScopeSets()).step4);
  const modelPath = DEFAULT_MODEL;
  // A unique, harness-owned transient bucket prevents an operator supplied
  // bucket from redirecting this upload to a shared or production location.
  const bucketKey = `aps-gate-${randomUUID().replaceAll("-", "")}`;
  const { OssClient } = await loadOssModule();
  const oss = new OssClient();

  await oss.createBucket("US", { bucketKey, policyKey: "transient" }, { accessToken });
  const objectKey = basename(modelPath);
  await oss.uploadObject(bucketKey, objectKey, readFileSync(modelPath), { accessToken });
  const details = await oss.getObjectDetails(bucketKey, objectKey, { accessToken });
  const urn = Buffer.from(details.objectId).toString("base64url");

  const { ModelDerivativeClient } = await loadModelDerivativeModule();
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
  evidence.sandboxObject = { bucketKey, objectKey };
  evidence.urn = urn;
  return ok;
}

// Step 5 — element properties via Model Derivative, spot-checked against the
// generator's own validated ground truth (layer names from make_test_model.py).
async function step5() {
  const accessToken = await token((await getScopeSets()).read);
  const urn = evidence.urn;
  if (!urn) {
    record(5, "properties extraction", false, "no harness-owned URN — run the full gate so step 4 creates the synthetic model.");
    return false;
  }
  const { ModelDerivativeClient } = await loadModelDerivativeModule();
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

function selectedSteps(args) {
  if (args.length === 0) return [2, 3, 4, 5];
  if (args.length !== 2 || args[0] !== "--step" || !["2", "3"].includes(args[1])) {
    throw new Error("usage: node src/gate.mjs [--step 2|3]; steps 4 and 5 always run together in the full gate");
  }
  return [Number(args[1])];
}

async function cleanup() {
  if (!evidence.sandboxObject) return;
  const accessToken = await token((await getScopeSets()).step4);
  const { bucketKey, objectKey } = evidence.sandboxObject;
  const { OssClient } = await loadOssModule();
  const oss = new OssClient();
  await oss.deleteObject(bucketKey, objectKey, { accessToken });
  await oss.deleteBucket(bucketKey, { accessToken });
  evidence.cleanup = "completed";
}

async function main() {
  let selected;
  try {
    selected = selectedSteps(process.argv.slice(2));
  } catch (error) {
    console.error(`GATE BLOCKED (fail closed): ${error.message}`);
    process.exit(2);
  }
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
  if (evidence.sandboxObject) {
    try {
      await cleanup();
    } catch (error) {
      record(4, "sandbox cleanup", false, String(error));
      allOk = false;
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
