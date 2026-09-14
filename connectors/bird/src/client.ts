import { BirdClient } from "@messagebird/sdk";

export class MissingBirdApiKey extends Error {
  constructor() {
    super("BIRD_API_KEY is not set. Export it in the local environment; never commit it.");
    this.name = "MissingBirdApiKey";
  }
}

export function birdApiKeyFromEnv(source: NodeJS.ProcessEnv = process.env): string {
  const key = (source.BIRD_API_KEY || "").trim();
  if (!key) {
    throw new MissingBirdApiKey();
  }
  return key;
}

export function createBirdClient(source: NodeJS.ProcessEnv = process.env): BirdClient {
  const key = birdApiKeyFromEnv(source);
  return new BirdClient({ apiKey: key });
}
