/**
 * Optional SMS OTP example using Bird's built-in bird_otp_verification template.
 *
 * Never auto-sent. Requires BIRD_SEND_OTP=1 and BIRD_OTP_TO. This file exists
 * so the request shape is reviewable; importing it does nothing.
 */
import { createBirdClient } from "./client.ts";

export const OTP_TEMPLATE = "bird_otp_verification";

export async function sendOtpExample(): Promise<{ id: string; status: string }> {
  if (process.env.BIRD_SEND_OTP !== "1") {
    throw new Error(
      "Refusing to send OTP: set BIRD_SEND_OTP=1 after reviewing BIRD_OTP_TO. Nothing is auto-sent."
    );
  }
  const to = (process.env.BIRD_OTP_TO || "").trim();
  if (!to) {
    throw new Error("BIRD_OTP_TO is required to send the OTP example.");
  }
  const bird = createBirdClient();
  const msg = await bird.sms.send({
    template: OTP_TEMPLATE,
    to,
    language: process.env.BIRD_OTP_LANGUAGE || "en",
    parameters: {
      code: process.env.BIRD_OTP_EXAMPLE_CODE || "000000",
    },
  });
  return { id: msg.id, status: msg.status };
}

async function main(): Promise<void> {
  if (process.env.BIRD_SEND_OTP !== "1") {
    console.log(
      `Dry run for template ${OTP_TEMPLATE}. Export BIRD_API_KEY, BIRD_OTP_TO, and BIRD_SEND_OTP=1 to send.`
    );
    return;
  }
  const result = await sendOtpExample();
  console.log(result.id, result.status);
}

const invokedDirectly = import.meta.url === `file://${process.argv[1]}`;
if (invokedDirectly) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 2;
  });
}
