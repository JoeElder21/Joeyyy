/**
 * Hello World email via @messagebird/sdk BirdClient.
 *
 * Does not send unless BIRD_SEND_HELLO=1. Recipients and the from-address
 * come from the environment so this public tree never holds Joe's address
 * or a key.
 *
 * Bird onboarding sender (set as BIRD_FROM): onboarding at messagebird.dev
 * Joe's requested destination: set BIRD_HELLO_TO (Bird order MT1FL8M9VY).
 */
import { createBirdClient } from "./client.ts";

function requireEnv(name: string): string {
  const value = (process.env[name] || "").trim();
  if (!value) {
    throw new Error(`${name} is required to send. This sample will not invent a recipient.`);
  }
  return value;
}

export async function sendHelloWorldEmail(): Promise<{ id: string; status: string }> {
  if (process.env.BIRD_SEND_HELLO !== "1") {
    throw new Error(
      "Refusing to send: set BIRD_SEND_HELLO=1 after reviewing the recipient. Nothing is auto-sent."
    );
  }
  const bird = createBirdClient();
  const msg = await bird.email.send({
    from: { email: requireEnv("BIRD_FROM"), name: "Joeyyy Bird sample" },
    to: [requireEnv("BIRD_HELLO_TO")],
    subject: "Hello World from Joeyyy",
    html: "<p>Hello World from the Joeyyy Bird sample. Order reference MT1FL8M9VY.</p>",
  });
  return { id: msg.id, status: msg.status };
}

async function main(): Promise<void> {
  if (process.env.BIRD_SEND_HELLO !== "1") {
    console.log(
      "Dry run. Export BIRD_API_KEY, BIRD_FROM, BIRD_HELLO_TO, and BIRD_SEND_HELLO=1 to send."
    );
    return;
  }
  const result = await sendHelloWorldEmail();
  console.log(result.id, result.status);
}

const invokedDirectly = import.meta.url === `file://${process.argv[1]}`;
if (invokedDirectly) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 2;
  });
}
