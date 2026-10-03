/**
 * Structural guardrails for the layered frontend (ADR-0040 §7).
 *
 * These checks exist because the rules they encode were not enforceable before
 * the restructure: `lib/` mixed pure functions with React "on purpose, as a
 * comment says", nothing stopped a page from importing a page, and a
 * 537-line context grew a notification poll, three contexts and an OAuth loader
 * in one file. A rule nobody checks is a comment, and the file it describes
 * grows.
 *
 * Every test here answers one question: what would it cost to break this?
 *
 * - **Import rules (#2–#9)** are the whole point of the layering. The arrow
 *   `shared → entities → features → widgets → pages → app` is what makes the
 *   structure worth having; a cycle or a backwards edge makes it decoration.
 * - **Public API (#10)** is what lets the next restructure touch a slice's
 *   internals without touching its 57 consumers.
 * - **Baselines (#16–#18, in `baseline.test.ts`)** catch a lost route, a lost
 *   CSS rule or a lost translation.
 * - **Budgets (#1)** are a ratchet: they exist so the 537-line file cannot come
 *   back unnoticed.
 *
 * Parsing goes through the TypeScript compiler API rather than regular
 * expressions. A regex that also matches inside a comment or a doc string
 * reports violations that are not there, and a guardrail that cries wolf is a
 * guardrail people delete.
 *
 * ## Stage 0: the soft mode
 *
 * The plan stages these checks so they are green BEFORE the code moves (§4,
 * step 3): a test that is red on honest code would have to be weakened as a
 * whole, and a weakened test protects nothing. Two knobs implement that:
 *
 * - `RESTRUCTURE_STARTED` — false while the flat folders are still in place.
 *   Checks that can only pass on the new layout are skipped, and `PENDING` names
 *   them, so nothing is silently dropped.
 * - The stage-status block below fails if `RESTRUCTURE_STARTED` is true while
 *   `PENDING` is non-empty, which makes "the layout is done but the checks were
 *   never turned on" an error rather than a state.
 *
 * Stage 10 flips the flag and every pending check becomes a real one.
 */

import { describe, expect, it } from "vitest";

import {
  LAYERS,
  allImports,
  collectImports,
  cssFiles,
  describeRef,
  importsOf,
  isTestFile,
  layerOf,
  listLayerFiles,
  listSourceFiles,
  readAllCss,
  repoText,
  testFiles,
  type ImportRef,
  type Layer,
} from "./structureHelpers.ts";

/**
 * False until the flat folders are gone. Flipped in stage 10 of the plan; see
 * the module doc comment for why the checks start soft.
 */
const RESTRUCTURE_STARTED = false;

/** Checks that only make sense once the layout exists, in reporting order. */
const PENDING: readonly string[] = [
  "#1 line budgets",
  "#2 shared/lib is React-free",
  "#3 shared does not import upward",
  "#4 entities knows no transport or router",
  "#5 features do not import widgets/pages/app",
  "#6 widgets do not import pages/app",
  "#7 pages do not import app",
  "#8 app is imported only by its own entry point",
  "#9 slices do not import their neighbours",
  "#10 only index.ts is reachable from outside",
  "#11 no utils.ts/helpers.ts/common.ts",
  "#12 page.css is wired through app/styles/index.css",
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Maximum lines per file, by slice prefix — longest match wins.
 *
 * The numbers are a ratchet, not a style rule: each sits above the size the
 * chosen group has after the split and below the size at which the group starts
 * mixing responsibilities again. A file that legitimately needs more becomes a
 * deliberate budget change with a reason, which is the point.
 */
const LINE_BUDGETS: ReadonlyArray<readonly [string, number]> = [
  ["shared/api/client", 140],
  ["shared/api/endpoints", 120],
  ["shared/api/index", 60],
  ["shared/types/index", 80],
  ["shared/i18n/locales", 120],
  ["shared/hooks", 250],
  ["shared/lib", 250],
  ["entities", 250],
  ["features", 300],
  ["widgets", 320],
  ["pages", 300],
  ["app", 200],
  ["app/styles", 400],
];

function budgetFor(path: string): number | null {
  let best: { prefix: string; limit: number } | null = null;
  for (const [prefix, limit] of LINE_BUDGETS) {
    if (!path.startsWith(prefix)) continue;
    if (!best || prefix.length > best.prefix.length) {
      best = { prefix, limit };
    }
  }
  return best?.limit ?? null;
}

/** Every file over its budget, as `path: lines (limit)`. */
function overBudget(): string[] {
  const problems: string[] = [];
  for (const file of listSourceFiles()) {
    // The generated schema is 2 862 lines of machine output; a line budget for
    // it would be a comment about openapi-typescript, not a rule.
    if (file.path.endsWith(".d.ts")) continue;
    // Test files are bounded by what they test, not by the structure: splitting
    // a 200-line test into three files to satisfy a budget makes it worse.
    if (isTestFile(file)) continue;
    const limit = budgetFor(file.path);
    if (limit !== null && file.lines > limit) {
      problems.push(`${file.path}: ${file.lines} lines (limit ${limit})`);
    }
  }
  return problems;
}

// ---------------------------------------------------------------------------
// Import rules
// ---------------------------------------------------------------------------

/** Layer of an import target, or null when it is outside the layered tree. */
function targetLayer(ref: { resolved: string | null }): Layer | null {
  if (!ref.resolved) return null;
  return layerOf({ path: ref.resolved, slice: "", text: "", lines: 0 });
}

/** Renders violations for a failure message, one import per line. */
function format(refs: ReadonlyArray<ImportRef>): string {
  return refs.map(describeRef).join("\n");
}

/** Imports from `slice` (including its sub-slices) into a forbidden layer. */
function importsIntoLayer(slice: Layer, forbidden: Layer): string[] {
  return importsOf(slice)
    .filter((ref) => targetLayer(ref) === forbidden)
    .map((ref) => describeRef(ref));
}

/** Direct sub-slices of a layer: `features/sync`, `widgets/topbar`, … */
function slicesOf(layer: Layer): string[] {
  return [
    ...new Set(
      listLayerFiles()
        .map((file) => file.slice)
        .filter((slice) => slice.startsWith(`${layer}/`)),
    ),
  ];
}

/** The slices directly under one slice, used by the neighbour rule (#9). */
function nestedSlicesOf(slice: string): string[] {
  return [
    ...new Set(
      listLayerFiles()
        .map((file) => file.slice)
        .filter((other) => other.startsWith(`${slice}/`)),
    ),
  ];
}

// ---------------------------------------------------------------------------
// Checks
// ---------------------------------------------------------------------------

describe("structure: line budgets", () => {
  it.runIf(RESTRUCTURE_STARTED)(
    "#1 keeps every module within its budget",
    () => {
      expect(overBudget()).toEqual([]);
    },
  );
});

describe("structure: layer directions", () => {
  it.runIf(RESTRUCTURE_STARTED)("#2 keeps shared/lib free of React", () => {
    // The comment in eslint.config.js claimed this layer was "deliberately
    // pure" while `resource.ts` and `signInChallenge.ts` imported React from
    // it. A pure layer is what makes it reusable without a renderer, and what
    // lets its tests stay synchronous.
    const offenders = importsOf("shared/lib").filter((ref) =>
      ref.specifier.startsWith("react"),
    );
    expect(format(offenders)).toBe("");
  });

  it.runIf(RESTRUCTURE_STARTED)(
    "#3 keeps shared/ from importing any layer",
    () => {
      // The arrow's tail: a `shared/` module that imports `entities/` inverts
      // the dependency for the whole tree, because everything depends on
      // `shared/`.
      const offenders = format(
        allImports().filter(
          (ref) =>
            ref.from.startsWith("shared/") && targetLayer(ref) !== null,
        ),
      );
      expect(offenders).toBe("");
    },
  );

  it.runIf(RESTRUCTURE_STARTED)(
    "#4 keeps entities/ free of transport and router",
    () => {
      // A domain rule that knows about `fetch` or `react-router-dom` cannot be
      // read without the app around it, and stops being a rule about the domain.
      const offenders = format(
        importsOf("entities").filter(
          (ref) =>
            ref.specifier === "../api.ts" ||
            ref.specifier.endsWith("/api/index.ts") ||
            ref.specifier === "react-router-dom" ||
            ref.specifier.includes("useResource") ||
            ref.specifier.includes("useAsyncResource"),
        ),
      );
      expect(offenders).toBe("");
    },
  );

  it.runIf(RESTRUCTURE_STARTED)(
    "#5 keeps features/ from knowing the shell",
    () => {
      for (const forbidden of ["widgets", "pages", "app"] as const) {
        expect(importsIntoLayer("features", forbidden)).toEqual([]);
      }
    },
  );

  it.runIf(RESTRUCTURE_STARTED)("#6 keeps widgets/ from knowing routes", () => {
    for (const forbidden of ["pages", "app"] as const) {
      expect(importsIntoLayer("widgets", forbidden)).toEqual([]);
    }
  });

  it.runIf(RESTRUCTURE_STARTED)(
    "#7 keeps pages/ from importing the app layer",
    () => {
      // A page that reaches into `app/` for a provider or a helper cannot be
      // rendered in a test or reused in another shell.
      expect(importsIntoLayer("pages", "app")).toEqual([]);
    },
  );

  it.runIf(RESTRUCTURE_STARTED)("#8 lets only app/main.tsx import app/", () => {
    // `app/` is the assembly layer. Anything importing it becomes part of the
    // assembly, which is how a "just a component" turns into a second entry
    // point nobody knows about.
    const offenders = format(
      allImports().filter(
        (ref) =>
          ref.resolved?.startsWith("app/") &&
          ref.from !== "app/main.tsx" &&
          !ref.from.startsWith("app/"),
      ),
    );
    expect(offenders).toBe("");
  });

describe("structure: public API", () => {
  it.runIf(RESTRUCTURE_STARTED)(
    "#10 reaches slices only through their index.ts",
    () => {
      // The rule that pays for the whole layering: with it, a slice's internals
      // can change without touching its consumers. Without it, `types.ts` had
      // 57 importers and could not be split at all.
      const offenders = format(
        allImports().filter((ref) => {
          const to = ref.resolved;
          if (!to) return false;
          const toSlice = to.slice(0, Math.max(0, to.lastIndexOf("/")));
          const fromSlice = ref.from.slice(
            0,
            Math.max(0, ref.from.lastIndexOf("/")),
          );
          // Inside one slice, an internal import is the normal way to reach a
          // sibling module — the rule is about crossing OUT of a slice.
          if (toSlice === fromSlice) return false;
          if (!toSlice || to.endsWith("/index.ts")) return false;
          return LAYERS.includes(toSlice.split("/")[0] as Layer);
        }),
      );
      expect(offenders).toBe("");
    },
  );
});

describe("structure: naming", () => {
  it.runIf(RESTRUCTURE_STARTED)(
    "#11 bans the four names that became a dump",
    () => {
      // `utils.ts`, `helpers.ts`, `common.ts`, `misc.ts` are not neutral: they
      // are what a barrel of code with no other name looks like. Shared code
      // lives in `shared/` with a name that says what it does.
      const banned = /\/(utils|helpers|common|misc)\.tsx?$/;
      const offenders = listSourceFiles()
        .filter((file) => banned.test(file.path))
        .map((file) => file.path);
      expect(offenders).toEqual([]);
    },
  );
});

describe("structure: styles", () => {
  it.runIf(RESTRUCTURE_STARTED)(
    "#12 wires page.css through app/styles/index.css",
    () => {
      // Importing a page stylesheet from a component makes the load order
      // depend on the module graph (Vite emits styles in traversal order),
      // which is how a rule that must override another silently stops doing so.
      const offenders = allImports()
        .filter(
          (ref) =>
            ref.specifier.endsWith(".css") &&
            !ref.from.startsWith("app/"),
        )
        .map((ref) => `${ref.from} -> ${ref.specifier}`);
describe("structure: generated types", () => {
  it("#13 points gen:api:file at the schema next to the code", () => {
    // The schema is generated from the backend's OpenAPI document
    // (`tools/dump_openapi.py` → `npm run gen:api:file`). A path that does not
    // match where the file actually lives means the next regeneration writes a
    // second copy that nothing imports.
    expect(repoText("frontend/package.json")).toContain(
      "src/shared/api/schema.d.ts",
    );
  });

  it("#14 points index.html at the app entry point", () => {
    // A stale entry path builds fine (Vite resolves nothing it is not asked
    // for) and produces an application with no root component.
    expect(repoText("frontend/index.html")).toContain("/src/app/main.tsx");
  });
});

describe("structure: suite", () => {
  it("#15 does not let the test count shrink", () => {
    // "We simplified it" and "we deleted the assertion" look identical in a
    // diff of a moved file. This is the number that tells them apart.
    const its = testFiles().reduce((total, file) => {
      const matches = file.text.match(/\bit\(/g);
      return total + (matches ? matches.length : 0);
    }, 0);
    expect(its).toBeGreaterThanOrEqual(204);
  });

  it("keeps the CSS walk honest", () => {
    // A structure check that silently reads zero files passes everything it is
    // asked, so the walk itself is asserted: the four stylesheets are 3 026
    // lines and no split of them may leave the tree without CSS at all.
    expect(cssFiles().length).toBeGreaterThanOrEqual(4);
    expect([...readAllCss().values()].join("").length).toBeGreaterThan(100_000);
  });
});

describe("structure: stage status", () => {
  it("never claims a finished restructure with checks still pending", () => {
    // The soft mode must be loud, and it must also be temporary: a guardrail
    // that is quietly disabled looks exactly like one that is passing, which is
    // how a plan silently stops being executed.
    if (RESTRUCTURE_STARTED) {
      expect(PENDING).toEqual([]);
    } else {
      expect(PENDING.length).toBe(12);
    }
  });

  it("sees every layer the plan defines", () => {
    // The walk has to reach all six layers, or every import rule above is
    // asserting over an empty set.
    const present = new Set(
      listSourceFiles()
        .map(layerOf)
        .filter((layer): layer is Layer => layer !== null),
    );
    if (RESTRUCTURE_STARTED) {
      expect([...present].sort()).toEqual([...LAYERS].sort());
    } else {
      // Before the restructure the layers do not exist yet; what must hold is
      // that the walk is finding files at all.
      expect(listLayerFiles().length).toBeGreaterThan(60);
    }
  });

  it("resolves every relative import it sees", () => {
    // An unresolved specifier is a typo, a moved file, or an extension the
    // resolver does not know; all three make the import rules above blind to
    // that edge.
    const unresolved = listLayerFiles()
      .flatMap(collectImports)
      .filter((ref) => ref.specifier.startsWith(".") && ref.resolved === null)
      .map(describeRef);
    expect(unresolved).toEqual([]);
  });
});
      expect(offenders).toEqual([]);
    },
  );
});
  it.runIf(RESTRUCTURE_STARTED)("#9 keeps sibling slices independent", () => {
    // `features/sync/` must not import `features/donate/`. When two features
    // need each other, the shared code belongs in `entities/` (a rule about
    // the domain) or `shared/` (a mechanism).
    const offenders: string[] = [];
    for (const slice of slicesOf("features")) {
      if (!slice.includes("/")) continue;
      const siblings = nestedSlicesOf(slice).filter(
        (other) => other !== slice && !other.startsWith(`${slice}/`),
      );
      for (const sibling of siblings) {
        offenders.push(
          ...format(
            importsOf(slice).filter((ref) =>
              ref.resolved?.startsWith(`${sibling}/`),
            ),
          ),
        );
      }
    }
    expect(offenders).toEqual([]);
  });
});