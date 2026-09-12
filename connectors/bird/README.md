# Bird client sample

Small TypeScript sample using `@messagebird/sdk` `BirdClient`. Agent 007
owns any live send. This connector never hardcodes a key.

Bird workspace order reference: `MT1FL8M9VY`.

## Setup

```bash
cd connectors/bird
npm install
cp .env.example .env
```

Set Joe's real key in the local `.env` or as a GitHub Actions secret named
`BIRD_API_KEY`. The sample reads **only** `process.env.BIRD_API_KEY`. Do not
paste the key into chat or commit it.

`.env.example` shows the key *shape* `bk_xxxxxxxxx`. That is a placeholder,
not a working credential.

Bird's shared onboarding sender is the `BIRD_FROM` value documented in the
TypeScript email quickstart (`onboarding` at `messagebird.dev`). Joe's Hello
World destination is `BIRD_HELLO_TO` — the Gmail address from the Bird
workspace, not a committed address.

## Hello World email (gated)

Nothing is sent unless every required variable is set **and**
`BIRD_SEND_HELLO=1`:

```bash
export BIRD_API_KEY=          # local or GitHub secret only
export BIRD_FROM=             # Bird onboarding sender
export BIRD_HELLO_TO=         # Joe's destination
export BIRD_SEND_HELLO=1
npm run hello
```

Without `BIRD_SEND_HELLO=1` the script prints a dry-run line and exits 0.

## SMS OTP template (optional, not auto-sent)

`src/otp-example.ts` shows the built-in `bird_otp_verification` template.
Importing the file does not send. Sending requires `BIRD_SEND_OTP=1` and
`BIRD_OTP_TO`.

```bash
export BIRD_SEND_OTP=1
export BIRD_OTP_TO=           # E.164 destination Joe has approved
npm run otp
```

## What this is not

- Not an APEX specialist and not a brain roster identity.
- Not a promotion of `apex_delivery_commander`.
- Not a standing scheduled sender. Section 9 still gates unattended
  third-party communication.
