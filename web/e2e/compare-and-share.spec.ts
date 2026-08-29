import { expect, test } from "@playwright/test";
import { API, openSeededOpening, signIn } from "./fixtures";

/**
 * Comparing two candidates.
 *
 * The arithmetic is covered in Python; what only a browser can show is that
 * picking two rows actually produces the screen, and that the sentence naming
 * the decisive criteria is on it.
 */
test.describe("comparing", () => {
  test("two candidates line up, and the gap is attributed to criteria", async ({ page }) => {
    await signIn(page);
    await openSeededOpening(page);

    await page.getByRole("button", { name: /compare candidates/i }).click();
    await expect(page.locator(".picking-note")).toContainText(/pick two/i);

    const rows = page.locator(".exhibit:not([disabled])");
    await rows.nth(0).click();
    await expect(page.locator(".picking-note")).toContainText(/one picked/i);
    await rows.nth(1).click();

    await expect(page.locator(".compare-verdict")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator(".compare-who")).toHaveCount(2);

    // The headline names where the difference lives, not merely that there is one.
    await expect(page.locator(".compare-decisive").first()).toBeVisible();

    // Each row is worth a stated number of points of the gap.
    await expect(page.locator(".compare-spread").first()).toContainText(/worth \d+ of the gap/i);
  });

  test("leaving compare mode restores the ordinary panel", async ({ page }) => {
    await signIn(page);
    await openSeededOpening(page);

    const toggle = page.getByRole("button", { name: /compare candidates/i });
    await toggle.click();
    const rows = page.locator(".exhibit:not([disabled])");
    await rows.nth(0).click();
    await rows.nth(1).click();
    await expect(page.locator(".compare")).toBeVisible();

    await toggle.click();
    await expect(page.locator(".compare")).toHaveCount(0);
  });
});

/**
 * The read-only link.
 *
 * Here the token *is* the credential, so what matters is what a stranger holding
 * it can and cannot see. This runs in a context with no session at all.
 */
test.describe("a shared shortlist", () => {
  test("opens without a session and never shows contact details", async ({ page, browser }) => {
    await signIn(page);
    await openSeededOpening(page);

    // Shortlist someone, so the link has something to show.
    await page.locator(".exhibit").first().click();
    await expect(page.locator(".plate-name")).toBeVisible();
    const shortlist = page.getByRole("button", { name: /^shortlist$/i });
    if (await shortlist.count()) {
      await shortlist.click();
      const reason = page.locator("textarea");
      if (await reason.count()) {
        await reason.fill("Strongest evidence on SQL and impact.");
        await page.getByRole("button", { name: /shortlist|confirm|save/i }).last().click();
      }
    }

    await page.getByRole("button", { name: /share the shortlist/i }).click();
    const link = page.locator(".share-made input, .share-made code, .share-made a").first();
    await expect(link).toBeVisible({ timeout: 10_000 });
    const url = (await link.inputValue().catch(() => link.textContent())) ?? "";
    expect(url).toMatch(/\/shared\/[A-Za-z0-9_-]{20,}/);

    // A different browser context: no cookies, no storage, nothing carried over.
    const stranger = await browser.newContext();
    const strangerPage = await stranger.newPage();
    await strangerPage.goto(url);

    // The real view, by its own class: a permissive selector would pass on an
    // error page just as happily.
    await expect(strangerPage.locator(".shared")).toBeVisible({ timeout: 10_000 });
    await expect(strangerPage.locator(".shared-role")).not.toBeEmpty();
    await expect(strangerPage.locator(".shared-meta")).toContainText(/read-only/i);
    const body = (await strangerPage.locator("body").textContent()) ?? "";
    expect(body).not.toMatch(/@example\.com/);
    expect(body).not.toMatch(/sign out/i);
    await stranger.close();
  });

  test("the panel itself stays closed without a session", async ({ browser }) => {
    const stranger = await browser.newContext();
    const page = await stranger.newPage();

    const response = await page.request.get(`${API}/api/v1/openings`);
    expect(response.status()).toBe(401);

    await stranger.close();
  });

  test("a token that means nothing is refused like an expired one", async ({ browser }) => {
    // Distinguishing them would tell a guesser they had found something real.
    const stranger = await browser.newContext();
    const page = await stranger.newPage();

    const response = await page.request.get(
      `${API}/api/v1/shared/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA`,
    );
    expect(response.status()).toBe(404);

    await stranger.close();
  });
});
