/**
 * Baseline snapshots of the restructure (ADR-0040, plan stage 0, step 4).
 *
 * The layer guardrails in `structure.test.ts` say "do not break the rules";
 * this file says "do not lose anything". Between them they catch the two
 * failure modes that a rename-and-move refactor actually produces:
 *
 * - a route that quietly disappeared while `App.tsx` was split into
 *   `app/router/` — the `/admin/*` catch-all is invisible until someone types
 *   a typo into the address bar;
 * - a CSS rule or a translation that did not survive the split, which looks
 *   exactly like an intentional deletion in the diff.
 *
 * **Every number below is an ETALON, not a measurement.** If a stage of the
 * plan deliberately adds or removes something, the number changes in the SAME
 * commit as that change — silently is the only unacceptable option.
 *
 * The numbers were taken on the working tree at commit `34511b9` by
 * `tools/count_frontend_layers.py` and the ad-hoc walk that became this file.
 */

import { describe, expect, it } from "vitest";

import {
  cssFiles,
  isTestFile,
  jsxAttributes,
  listSourceFiles,
  readAllCss,
  testFiles,
} from "./structureHelpers.ts";

/**
 * Routes, in declaration order.
 *
 * 20 entries: 18 pages plus two catch-all redirects (`/admin/*` in the console
 * shell and in the public shell). The two are counted separately on purpose —
 * they live in different shells, and a refactor that drops one of them sends a
 * typo to the public dashboard instead of the console root.
 */
const ROUTES: readonly string[] = [
  "/",
  "/subjects",
  "/subjects/:courseId/grades",
  "/subjects/:courseId/students/:studentId",
  "/subjects/:courseId/assignments/:courseworkId",
  "/subjects/:courseId",
  "/assignments",
  "/grades",
  "/calendar",
  "/feedback",
  "/feedback/new",
  "/feedback/tickets",
  "/feedback/tickets/:id",
  "/settings",
  "/admin/*",
  "/admin",
  "/admin/feedback",
  "/admin/feedback/:id",
  "/admin/admins",
  "/admin/*",
];

/**
 * `<Route path="…">` literals, found through the AST.
 *
 * Location-agnostic on purpose: before the restructure the routes are declared
 * in `src/App.tsx`, after it in `src/app/router/routes.tsx`, and this snapshot
 * has to mean the same thing at both ends. Scanning every non-test file also
 * means a route added to a *second* place is counted, not silently accepted.
 */
function routeLiterals(): string[] {
  const found: string[] = [];
  for (const file of listSourceFiles()) {
    if (isTestFile(file)) continue;
    for (const ref of jsxAttributes(file.text, file.path, "Route", "path")) {
      found.push(ref);
    }
  }
  return found;
}

/**
 * `it(` occurrences across the suite.
 *
 * Counted as source occurrences, not as executed tests: the point is to catch
 * a test that was deleted or neutered, and a run count cannot distinguish
 * "one test, two assertions" from "two tests".
 */
function countIts(): number {
  return listSourceFiles()
    .filter(isTestFile)
    .reduce((total, file) => {
      const matches = file.text.match(/\bit\(/g);
      return total + (matches ? matches.length : 0);
    }, 0);
}

/**
 * Unique CSS selectors across every stylesheet.
 *
 * Set, not list: a rule that is cut out of `pages.css` and pasted into
 * `pages/subjects/page.css` keeps the same selector, which is exactly what must
 * not count as a change. Whitespace is normalised so a re-indent during the
 * move cannot move the number either.
 */
function cssSelectors(): Set<string> {
  const selectors = new Set<string>();
  for (const text of readAllCss().values()) {
    const withoutComments = text.replace(/\/\*[\s\S]*?\*\//g, "");
    for (const block of withoutComments.matchAll(/([^{}]+)\{/g)) {
      for (const part of block[1].split(",")) {
        const selector = part.replace(/\s+/g, " ").trim();
        if (selector && !selector.startsWith("@")) {
          selectors.add(selector);
        }
      }
    }
  }
  return selectors;
}

/**
 * Keys of one locale dictionary.
 *
 * Read from the file that exports it rather than from a glob over
 * `locales/<lang>/**`: the dictionaries are SPLIT into seven domain files per
 * language during the restructure (ADR-0040 §4), and each of the seven must
 * still answer to the same key set. Importing the merged `index.ts` keeps this
 * independent of how many files the split produced — and importing it (not
 * parsing the text) is what makes `tsc` and this snapshot agree by
 * construction.
 */
async function localeKeys(lang: "en" | "uk" | "ru"): Promise<string[]> {
  const module = await import(`../i18n/${lang}.ts`);
  return Object.keys(module[lang]).sort();
}

/** Keys a dictionary must carry. `en` defines them; the others mirror them. */
const I18N_KEY_COUNT = 395;

describe("baseline: routes", () => {
  it("keeps every declared route, in order", () => {
    expect(routeLiterals()).toEqual([...ROUTES]);
  });

  it("declares both catch-all redirects (`/admin/*`)", () => {
    // One lives in the console shell and one in the public shell. A typo must
    // land on `/admin`, never on the public dashboard — and the fact that there
    // are two of them is easy to lose when the routes become data (ADR-0036).
    const catchAlls = routeLiterals().filter((route) => route === "/admin/*");
    expect(catchAlls).toHaveLength(2);
  });
});

describe("baseline: test suite", () => {
  it("keeps at least 204 test cases", () => {
    // A floor, not an equality: a stage may legitimately add tests. What it may
    // never do is remove one without saying so — "we simplified it" and "we
    // deleted the assertion" look identical in a diff of a moved file.
    expect(countIts()).toBeGreaterThanOrEqual(204);
  });

  it("keeps the suite spread over at least 33 files", () => {
    expect(testFiles().length).toBeGreaterThanOrEqual(33);
  });
});

describe("baseline: stylesheets", () => {
  it("keeps every CSS selector", () => {
    // The set of selectors, not the number of files: `pages.css` is split into
    // nine during the restructure and every rule has to arrive somewhere. A lost
    // selector is a silently unstyled element.
    //
    // Comments are stripped before counting, so the number is 469 rather than
    // the 560 a naive scan of the same four files reports — most of the
    // difference is the section banners in `pages.css`, which are prose, not
    // selectors.
    expect(cssSelectors().size).toBe(469);
  });

  it("keeps the stylesheets themselves in the app layer", () => {
    // The CSS files are the visual half of the structure, so their paths move
    // with everything else; this asserts that the walk actually sees them
    // (an empty walk would satisfy the count check above by accident).
    expect(cssFiles().length).toBeGreaterThanOrEqual(4);
  });
});

describe("baseline: translations", () => {
  it("keeps 395 keys in English", async () => {
    expect((await localeKeys("en")).length).toBe(I18N_KEY_COUNT);
  });

  it("keeps 395 keys in Ukrainian", async () => {
    expect((await localeKeys("uk")).length).toBe(I18N_KEY_COUNT);
  });

  it("keeps 395 keys in Russian", async () => {
    expect((await localeKeys("ru")).length).toBe(I18N_KEY_COUNT);
  });

  it("keeps the three dictionaries identical in key set", async () => {
    // ADR-0011 makes `tsc` catch a missing key; this catches the OTHER
    // direction — a key left behind in `uk`/`ru` after it was dropped from `en`
    // would survive the build and quietly keep a string nobody can reach.
    const [en, uk, ru] = await Promise.all([
      localeKeys("en"),
      localeKeys("uk"),
      localeKeys("ru"),
    ]);
    expect(uk).toEqual(en);
    expect(ru).toEqual(en);
  });
});