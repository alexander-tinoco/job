import { expect, test } from "@playwright/test";
import { openSeededOpening, resumePdf, signIn } from "./fixtures";

/**
 * The applicant's journey. Nothing else in the project exercises it end to end:
 * the API tests post a form directly, which cannot tell you that the consent box
 * is unchecked or that the confirmation screen exists.
 */
test.describe("applying", () => {
  test("a candidate can apply, and is asked to confirm first", async ({ page }) => {
    const email = `e2e.${Date.now()}@example.com`;
    await page.goto("/apply/data-analyst-demo");

    await expect(page.getByRole("heading", { name: /data analyst/i })).toBeVisible();

    await page.locator('input[name="full_name"]').fill("Rosa Delgado");
    await page.locator('input[name="email"]').fill(email);
    await page.setInputFiles('input[type="file"]', {
      name: "cv.pdf",
      mimeType: "application/pdf",
      buffer: resumePdf("Rosa Delgado"),
    });

    // An application cannot be unsent, so it is confirmed before it goes.
    const consent = page.locator('input[type="checkbox"]');
    await expect(consent).not.toBeChecked();
    await consent.check();
    await page.getByRole("button", { name: /send application/i }).click();

    await expect(page.getByRole("heading", { name: /send your application\?/i })).toBeVisible();
    await page.getByRole("button", { name: /send it/i }).click();

    await expect(page).toHaveURL(/\/received\//, { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: /your application is in/i })).toBeVisible();
    // The promise the product is actually making, on the screen that makes it.
    await expect(page.getByText(/none is filtered out automatically/i)).toBeVisible();
    await expect(page.locator(".reference")).toContainText(/Reference \w{8}/);
  });

  test("consent is required and unchecked by default", async ({ page }) => {
    await page.goto("/apply/data-analyst-demo");

    const consent = page.locator('input[type="checkbox"]');
    await expect(consent).not.toBeChecked();
    await expect(page.getByRole("button", { name: /send application/i })).toBeDisabled();
  });

  test("an opening that does not exist says so rather than breaking", async ({ page }) => {
    await page.goto("/apply/no-such-opening");
    await expect(page.getByRole("heading", { name: /not available/i })).toBeVisible();
  });
});

/**
 * The panel is behind a sign-in, and the sign-in is what actually protects it —
 * not the unguessable path.
 */
test.describe("the panel", () => {
  test("the panel is unreachable without signing in", async ({ page }) => {
    await page.goto(`/${process.env.VITE_PANEL_PATH ?? "panel"}`);
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    await expect(page.locator(".exhibit")).toHaveCount(0);
  });

  test("wrong credentials say the same thing for every cause", async ({ page }) => {
    // A fresh address each run. The limiter counts failures per email, so a
    // fixed one would lock itself out and this test would start asserting the
    // lockout message instead — which is exactly what happened while writing it.
    const unknown = `nobody.${Date.now()}@example.com`;
    await page.goto(`/${process.env.VITE_PANEL_PATH ?? "panel"}`);
    await page.locator('input[type="email"]').fill(unknown);
    await page.locator('input[type="password"]').fill("not-the-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Never "no such account": that would turn the form into a way to find out
    // who has one.
    await expect(page.getByText(/email or password incorrect/i)).toBeVisible();
    await expect(page.getByText(/no such|not found|unknown/i)).toHaveCount(0);
  });

  test("repeated attempts are throttled, and say so", async ({ page }) => {
    const target = `locked.${Date.now()}@example.com`;
    // From an address of its own. Failures are counted per IP as well as per
    // email, so hammering from the suite's own address spends an allowance every
    // later sign-in needs — which is precisely how this test broke the five that
    // follow it, once, quietly, and only when the whole file ran.
    await page.setExtraHTTPHeaders({ "X-Forwarded-For": "203.0.113.42" });
    await page.goto(`/${process.env.VITE_PANEL_PATH ?? "panel"}`);

    for (let attempt = 0; attempt < 6; attempt++) {
      await page.locator('input[type="email"]').fill(target);
      await page.locator('input[type="password"]').fill("not-the-password");
      await page.getByRole("button", { name: /sign in/i }).click();
      await expect(page.locator(".notice-error")).toBeVisible();
    }

    // The one case where the message is allowed to differ: telling someone their
    // password is wrong while the account is throttled would have them retry for
    // fifteen minutes, and it reveals nothing about whether the account exists.
    await expect(page.getByText(/too many attempts/i)).toBeVisible();
  });

  test("candidates are ranked, and every score is backed by the résumé", async ({ page }) => {
    await signIn(page);
    await openSeededOpening(page);

    const rows = page.locator(".exhibit");
    await expect(rows.first()).toBeVisible();

    const scores = await page
      .locator(".exhibit-score")
      .evaluateAll((nodes) => nodes.map((n) => Number(n.textContent)));
    expect(scores.length).toBeGreaterThan(1);
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);

    await rows.first().click();
    await expect(page.locator(".plate-name")).toBeVisible();

    // Every finding cites a sentence and the character offsets it sits at. That
    // pairing is the product's whole claim: the score is not an opinion, it is
    // a quote you can go and check.
    const evidence = page.locator("button.locator").first();
    await expect(evidence).toBeVisible();
    await expect(evidence.locator(".offset")).toContainText(/at \d+–\d+/);
  });

  test("hovering a finding lifts its quote in the résumé", async ({ page }) => {
    // The signature interaction, and one no API test can see.
    await signIn(page);
    await openSeededOpening(page);
    await page.locator(".exhibit").first().click();
    await expect(page.locator(".plate-name")).toBeVisible();

    const finding = page.locator("button.locator").first();
    await finding.hover();

    // The document marks every located quote; hovering makes *this* one active.
    await expect(page.locator('mark[data-active="true"]').first()).toBeVisible({ timeout: 5_000 });
  });
});
