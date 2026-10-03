/**
 * Shared helpers for the structural guardrails (ADR-0040, stage 0).
 *
 * Three things live here and nowhere else:
 *
 * 1. **The file walk.** `structure.test.ts` needs every source file with its
 *    text, and `baseline.test.ts` needs the same walk with different filters.
 *    One implementation means the guardrails cannot drift apart — a check that
 *    reads a different set of files is a check of something else.
 * 2. **Import extraction through the TypeScript compiler API**, not through
 *    regular expressions. `vi.mock("../api.ts")` and `from "../api.ts"` are both
 *    string literals, and both matter for the guardrails; a regex that also
 *    matches inside a comment or a doc string produces a violation that is not
 *    there, and a guardrail that cries wolf is a guardrail people disable.
 * 3. **The slice of a path.** Every rule below is phrased as "a file in layer X
 *    may not import Y", so they all need the same notion of a layer and a
 *    slice, and they must agree on it.
 *
 * The walk uses `node:fs` rather than `import.meta.glob`: Vitest does not
 * process CSS imports (`css: false` is the default), so a globbed stylesheet
 * arrives as an empty string and a selector snapshot over it would silently
 * compare nothing against nothing. Reading the files keeps the check honest for
 * every extension.
 *
 * The root is derived from `import.meta.url` through `fileURLToPath` on the raw
 * string. `new URL("..", import.meta.url)` — the obvious spelling — throws
 * `ERR_INVALID_URL_SCHEME` under the jsdom environment, which replaces the
 * global `URL` with the browser one that refuses non-HTTP input.
 *
 * `typescript` is already a devDependency (it is what `npm run build` runs), so
 * parsing costs no new dependency.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

/** Absolute path of `frontend/src`, derived from this file's own location. */
export const SRC_ROOT = fileURLToPath(`${import.meta.url}/../..`);

/** Absolute path of the repository root (three levels above `frontend/src`). */
export const REPO_ROOT = resolve(SRC_ROOT, "..", "..");

export type SourceFile = {
  /** Path relative to `frontend/src`, always with `/` separators. */
  path: string;
  /** The directory a file lives in, e.g. `entities/feedback`. */
  slice: string;
  text: string;
  lines: number;
};

const SOURCE_EXTENSIONS = [".ts", ".tsx"];

function walk(dir: string, out: string[]): void {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full, out);
    } else {
      out.push(full);
    }
  }
}

/** Absolute paths of every file under `src/`. */
function allFiles(): string[] {
  const out: string[] = [];
  walk(SRC_ROOT, out);
  return out;
}

function toSrcPath(file: string): string {
  return relative(SRC_ROOT, file).split(sep).join("/");
}

/**
 * Layers, lowest first. The order is the only allowed direction of dependency:
 * a module may import from a layer below its own, never from one above and
 * never from its own neighbours (ADR-0040 §3.2).
 */
export const LAYERS = [
  "shared",
  "entities",
  "features",
  "widgets",
  "pages",
  "app",
] as const;

export type Layer = (typeof LAYERS)[number];

/** Every source file under `src/`, tests and the generated schema included. */
export function listSourceFiles(): SourceFile[] {
  return allFiles()
    .filter((file) => SOURCE_EXTENSIONS.some((ext) => file.endsWith(ext)))
    .map((file) => {
      const path = toSrcPath(file);
      const text = readFileSync(file, "utf-8");
      return {
        path,
        slice: path.slice(0, Math.max(0, path.lastIndexOf("/"))),
        text,
        lines: text.split("\n").length,
      };
    })
    .sort((a, b) => a.path.localeCompare(b.path));
}

/** Only the layers, so a test never asserts anything about `src/test/` itself. */
export function listLayerFiles(): SourceFile[] {
  return listSourceFiles().filter((file) => file.slice !== "test");
}

export function isTestFile(file: SourceFile): boolean {
  return file.path.endsWith(".test.ts") || file.path.endsWith(".test.tsx");
}

/** A `*.test.ts(x)` file — where the shipped suite lives, per `vitest.config.ts`. */
export function testFiles(): SourceFile[] {
  return listSourceFiles().filter(isTestFile);
}

/** Text of one `src`-relative source file. */
export function sourceText(path: string): string {
  return readFileSync(join(SRC_ROOT, path), "utf-8");
}

/** Text of one repository-root-relative file (`index.html`, `package.json`). */
export function repoText(path: string): string {
  return readFileSync(join(REPO_ROOT, path), "utf-8");
}

/** Paths of every CSS file, relative to `src/` and sorted. */
export function cssFiles(): string[] {
  return allFiles()
    .filter((file) => file.endsWith(".css"))
    .map(toSrcPath)
    .sort();
}

/** Every CSS file's text, keyed by its path relative to `src/`. */
export function readAllCss(): Map<string, string> {
  return new Map(
    allFiles()
      .filter((file) => file.endsWith(".css"))
      .map((file) => [toSrcPath(file), readFileSync(file, "utf-8")]),
  );
}

/** The layer a file belongs to, or null when it is not inside a layer. */
export function layerOf(file: SourceFile): Layer | null {
  const top = file.slice.split("/")[0];
  return (LAYERS as readonly string[]).includes(top) ? (top as Layer) : null;
}

/** A module specifier together with the file that asked for it. */
export type ImportRef = {
  /** `src`-relative path of the importing file. */
  from: string;
  /** `src`-relative path of the importing file's directory. */
  fromDir: string;
  /** The literal as written, e.g. `../api.ts`. */
  specifier: string;
  /**
   * The resolved target, `src`-relative, or null for a bare package specifier
   * (`react`, `lucide-react`) — i.e. for everything the layer rules do not
   * govern.
   */
  resolved: string | null;
};

/**
 * Resolves a relative specifier against the importing file.
 *
 * The project convention is an explicit extension (ADR-0005 +
 * `allowImportingTsExtensions`), so the literal already names a real file; the
 * tolerance here is a specifier written without one, resolved by trying `.ts`,
 * `.tsx` and `/index.ts` in that order.
 *
 * Existence is decided against the globbed file list rather than the disk, so
 * the answer does not depend on the working directory the suite was started
 * from — and a specifier that points at a file which does not exist resolves to
 * null, which is exactly the case guardrail #10 must be able to talk about.
 */
function resolveSpecifier(fromDir: string, specifier: string): string | null {
  if (!specifier.startsWith(".")) {
    return null;
  }
  const stack = fromDir ? fromDir.split("/") : [];
  for (const segment of specifier.split("/")) {
    if (segment === "." || segment === "") continue;
    if (segment === "..") {
      stack.pop();
    } else {
      stack.push(segment);
    }
  }
  const base = stack.join("/");
  const candidates =
    specifier.endsWith(".ts") || specifier.endsWith(".tsx")
      ? [base]
      : [`${base}.ts`, `${base}.tsx`, `${base}/index.ts`];
  for (const path of candidates) {
    if (statSync(join(SRC_ROOT, path), { throwIfNoEntry: false })) {
      return path;
    }
  }
  return null;
}

/** Rendered for a failure message: enough to find the line without a debugger. */
export function describeRef(ref: ImportRef): string {
  return `${ref.from} -> ${ref.specifier} (${ref.resolved ?? "?"})`;
}

/**
 * Literal values of a JSX attribute on elements of one tag name.
 *
 * `<Route path="/feedback" …>` yields `/feedback`. Used by the route snapshot
 * (ADR-0040 §4), which must survive the move of the route table from
 * `src/App.tsx` to `src/app/router/` without being rewritten to match — a
 * snapshot that has to be edited at every step is a snapshot nobody reads.
 */
export function jsxAttributes(
  text: string,
  fileName: string,
  tag: string,
  attribute: string,
): string[] {
  const source = ts.createSourceFile(
    fileName,
    text,
    ts.ScriptTarget.Latest,
    true,
    fileName.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const values: string[] = [];
  const visit = (node: ts.Node): void => {
    if (
      (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) &&
      node.tagName.getText(source) === tag
    ) {
      for (const prop of node.attributes.properties) {
        if (
          ts.isJsxAttribute(prop) &&
          prop.name.getText(source) === attribute &&
          prop.initializer &&
          ts.isStringLiteral(prop.initializer)
        ) {
          values.push(prop.initializer.text);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return values;
}
/** `vi.mock("...")`, `import("...")` and every import/export declaration. */
export function collectImports(file: SourceFile): ImportRef[] {
  const found: ImportRef[] = [];
  const add = (specifier: string) => {
    found.push({
      from: file.path,
      fromDir: file.slice,
      specifier,
      resolved: resolveSpecifier(file.slice, specifier),
    });
  };

  const source = ts.createSourceFile(
    file.path,
    file.text,
    ts.ScriptTarget.Latest,
    true,
    file.path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );

  const visit = (node: ts.Node): void => {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      add(node.moduleSpecifier.text);
    } else if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === "vi" &&
      node.arguments.length === 1
    ) {
      // `vi.mock("../api.ts", factory)` — the factory argument is optional.
      const [first] = node.arguments;
      if (first && ts.isStringLiteral(first)) {
        add(first.text);
      }
    } else if (
      ts.isImportTypeNode(node) &&
      ts.isLiteralTypeNode(node.argument) &&
      ts.isStringLiteral(node.argument.literal)
    ) {
      add(node.argument.literal.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

/** Resolved imports of every file of one slice (the slice itself included). */
export function importsOf(slice: string): ImportRef[] {
  return listLayerFiles()
    .filter(
      (file) => file.slice === slice || file.slice.startsWith(`${slice}/`),
    )
    .flatMap(collectImports)
    .filter((ref) => ref.resolved !== null);
}

/** Every resolved import in the tree, one flat list. */
export function allImports(): ImportRef[] {
  return listLayerFiles()
    .flatMap(collectImports)
    .filter((ref) => ref.resolved !== null);
}