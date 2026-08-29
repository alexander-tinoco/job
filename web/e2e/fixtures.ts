import { expect, type Page, type APIRequestContext } from "@playwright/test";

export const PANEL = `/${process.env.VITE_PANEL_PATH ?? "panel"}`;
export const API = process.env.E2E_API_URL ?? "http://localhost:8000";

export const DEMO = { email: "demo@acme.com", password: "correct-horse-battery" };

/** A résumé PDF, built in the browser-agnostic way: bytes, not a fixture file. */
export function resumePdf(name: string): Buffer {
  const text = `${name} — Data Analyst. Eight years of SQL, dbt and experimentation.`;
  const body = `BT /F1 11 Tf 40 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${body.length} >>\nstream\n${body}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

export async function signIn(page: Page): Promise<void> {
  await page.goto(PANEL);
  // By input type, not by label: the password field wraps its input in a div
  // for the visibility toggle, so the label is not associated with it.
  await page.locator('input[type="email"]').fill(DEMO.email);
  await page.locator('input[type="password"]').fill(DEMO.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  // The panel chrome, not a candidate row: the first opening in the picker may
  // legitimately be empty, and waiting for a row here would fail before
  // `openSeededOpening` ever gets to choose one.
  await expect(page.getByRole("button", { name: /sign out/i })).toBeVisible({ timeout: 15_000 });
}

export const SEEDED_SLUG = "data-analyst-demo";

/**
 * Select the seeded opening in the panel.
 *
 * By id from the API rather than by walking the picker: a development database
 * accumulates openings, the picker shows titles that repeat, and the first entry
 * is often an empty one. Asking which id belongs to the seeded slug makes this
 * independent of how much is lying around.
 */
export async function openSeededOpening(page: Page): Promise<void> {
  const response = await page.request.get(`${API}/api/v1/openings`);
  expect(response.ok(), "the panel session should be usable from the API too").toBeTruthy();
  const openings = (await response.json()) as { id: string; slug: string }[];
  const seeded = openings.find((o) => o.slug === SEEDED_SLUG);
  expect(seeded, `no opening with slug ${SEEDED_SLUG} — is the seed loaded?`).toBeTruthy();

  // Whose ranking are we waiting for? The panel opens on whichever opening comes
  // first, and that one already has rows — so waiting for "a row" passes
  // instantly and a click can land on the previous opening's candidate before
  // the new list arrives. Wait for a name that belongs to *this* opening.
  const ranked = await page.request.get(
    `${API}/api/v1/openings/${seeded!.id}/applications?limit=1`,
  );
  const top = (await ranked.json()).items[0]?.candidate_name as string | undefined;

  const picker = page.locator("select.field");
  if (await picker.count()) {
    await picker.selectOption(seeded!.id);
  }
  if (top) {
    await expect(page.locator(".exhibit-name", { hasText: top }).first()).toBeVisible({
      timeout: 15_000,
    });
  }
  await expect(page.locator(".exhibit").first()).toBeVisible({ timeout: 15_000 });
}

/** Signs in through the API so a test can set something up without the UI. */
export async function apiSignIn(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${API}/api/v1/auth/login`, { data: DEMO });
  expect(response.ok()).toBeTruthy();
}
