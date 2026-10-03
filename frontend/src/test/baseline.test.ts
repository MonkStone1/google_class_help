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
  listSourceFiles,
  readAllCss,
  sourceText,
  testFiles,
} from "./structureHelpers.ts";

/**
 * Routes, in declaration order.
 *
 * 20 entries: 18 pages plus the two catch-all redirects — `/admin/*` (a console
 * typo stays in the console) and `*` (anything else goes home). Both are
 * counted separately on purpose: dropping one sends a mistyped console URL to
 * the public dashboard, which is confusing enough on its own.
 *
 * Read from the route TABLE now that it is data (`app/router/routes.tsx`), not
 * from JSX: the point of the split was to stop making a route unreadable
 * without the shell around it.
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
  "*",
];

/** The `path` values declared in the route table, in order. */
function routeLiterals(): string[] {
  const table = sourceText("app/router/routes.tsx");
  // The table holds the eighteen pages. The two redirects are not in it — they
  // belong to the SHELLS, and `AppRouter` keeps them next to the branch they
  // bound, which is why `/admin/*` appears once for the user branch and once
  // as the branch's catch-all.
  const declared = [...table.matchAll(/\bpath:\s*"([^"]+)"/g)].map((m) => m[1]);
  const redirects = [
    ...sourceText("app/router/AppRouter.tsx").matchAll(/path="([^"]+)"\s+element=\{<Navigate/g),
  ].map((m) => m[1]);
  // `AppRouter` reads the routes in the order the visitor hits them: the user
  // branch, its console redirect, the console branch, and finally the redirect
  // for everything else. Rebuilding that order here is what makes a moved route
  // visible as a baseline failure rather than as a surprise in production.
  const consoleRedirects = redirects.filter((route) => route !== "*");
  const homeRedirects = redirects.filter((route) => route === "*");
  return [
    ...declared.slice(0, 14),
    ...consoleRedirects,
    ...declared.slice(14),
    ...homeRedirects,
  ];
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
  const module = await import(`../shared/i18n/locales/${lang}.ts`);
  return Object.keys(module[lang]).sort();
}

/** Keys a dictionary must carry. `en` defines them; the others mirror them. */
const I18N_KEY_COUNT = 395;

describe("baseline: routes", () => {
  it("keeps every declared route, in order", () => {
    expect(routeLiterals()).toEqual([...ROUTES]);
  });

  it("keeps both catch-all redirects", () => {
    // `/admin/*` sends a console typo to the console root; `*` sends anything
    // else home. The fact that there are TWO is easy to lose when the routes
    // become data, and losing one is invisible until someone types a bad URL.
    const routes = routeLiterals();
    expect(routes.filter((route) => route === "/admin/*")).toHaveLength(1);
    expect(routes).toContain("*");
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