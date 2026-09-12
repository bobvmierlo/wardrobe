/**
 * Checks the test environment is the one the tests assume, before they run.
 *
 * Everything under test here talks to `localStorage` or `fetch`, and when jsdom
 * comes up without them the failure reads as "Cannot read properties of
 * undefined (reading 'clear')" from whichever test touched it first — which
 * says nothing about the cause and sent one CI failure on a long detour. So the
 * environment gets checked once, by name.
 */

import { beforeEach } from "vitest";

const required = ["localStorage", "fetch", "location", "document"] as const;

for (const name of required) {
  if (typeof (globalThis as Record<string, unknown>)[name] === "undefined") {
    throw new Error(
      `De testomgeving mist '${name}'. Verwacht is jsdom met een echte origin` +
        ` (zie test.environmentOptions in vite.config.ts); jsdom weigert` +
        ` localStorage op een opaque origin.`,
    );
  }
}

beforeEach(() => {
  // Nobody should inherit the previous test's stored state, whichever file it
  // came from.
  localStorage.clear();
});
