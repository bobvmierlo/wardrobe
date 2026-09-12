import { expect, test } from "@playwright/test";

/**
 * The path somebody walks the first time they use the app: log in, add a
 * garment, find it back.
 *
 * Deliberately one test and deliberately shallow. The backend suite already
 * proves every API path, and the unit tests cover the logic that is easy to get
 * wrong. What only a browser can tell you is whether the React app renders at
 * all against the real server and whether its buttons reach those paths — a
 * class of breakage (a bad build, a route that 404s, a form that posts the wrong
 * shape) that every other test in this repo would sail straight past.
 *
 * No arbitrary waits: every step is a web-first assertion or an action that
 * waits on its own. A sleep here is how an end-to-end suite becomes the thing
 * nobody trusts.
 */

const ADMIN = "admin";
const PASSWORD = "e2e-wachtwoord";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  // The login screen asks the server what it may offer before it draws, so wait
  // for the form rather than for a moment in time.
  const username = page.locator('input[autocomplete="username"]');
  await expect(username).toBeVisible();
  await username.fill(ADMIN);
  await page.locator('input[autocomplete="current-password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Inloggen" }).click();
}

test("a newcomer logs in, adds a garment and finds it back", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text()}`);
  });

  await signIn(page);

  // Landed in their own kast.
  await expect(page.getByRole("heading", { name: /Mijn kast/ })).toBeVisible();

  // Add a garment. The name is unique per run so a re-run on the same database
  // cannot pass on the previous run's leftovers.
  const name = `Testtrui ${Date.now()}`;
  await page.getByRole("button", { name: "Kledingstuk toevoegen" }).click();
  await expect(page.getByRole("heading", { name: "Nieuw stuk" })).toBeVisible();

  await page.getByPlaceholder("bijv. Donkerblauwe polo").fill(name);
  // The categories come from the server, so pick whatever it actually offered
  // instead of hard-coding a label the catalogue might not have.
  const category = page.locator("select").first();
  await expect(category.locator("option:not([disabled])").first()).toBeAttached();
  await category.selectOption({ index: 1 });
  await page.getByPlaceholder("bijv. Donkerblauw", { exact: true }).fill("Donkerblauw");

  // The label names the kast you are adding to ("Toevoegen aan kast", or the
  // kast's own name when it is shared with you), so match the verb rather than
  // the whole sentence.
  await page.getByRole("button", { name: /^Toevoegen aan/ }).click();

  // Saving goes straight to the garment's own page.
  await expect(page.getByRole("heading", { name })).toBeVisible();

  // And it is in the kast, which is the part that proves the server kept it.
  await page.goto("/");
  await expect(page.getByText(name)).toBeVisible();

  // A reload proves the session survived rather than the state being in memory.
  await page.reload();
  await expect(page.getByText(name)).toBeVisible();

  expect(problems, `the browser reported problems:\n${problems.join("\n")}`).toEqual([]);
});

test("a wrong password is refused and says so", async ({ page }) => {
  await page.goto("/login");
  await page.locator('input[autocomplete="username"]').fill(ADMIN);
  await page.locator('input[autocomplete="current-password"]').fill("niet-het-wachtwoord");
  await page.getByRole("button", { name: "Inloggen" }).click();

  // The server's own words, not "Sessie verlopen" — which is what this said
  // before, and which is a baffling thing to read when you simply mistyped.
  await expect(page.getByText(/Onjuiste gebruikersnaam of wachtwoord/)).toBeVisible();
  // Still on the login screen, not half-way into the app.
  await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible();
});

test("the front door says it is invitation-only", async ({ page }) => {
  // The default, and the thing a stranger needs to be told.
  await page.goto("/login");
  await expect(page.getByText(/Alleen op uitnodiging/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Account aanmaken" })).toHaveCount(0);
});
