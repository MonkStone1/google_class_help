import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/shared/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // Classic hooks rules only: the React Compiler ruleset shipped with
      // eslint-plugin-react-hooks v7 rejects the documented "adjust state
      // during render" pattern that lib/resource.ts relies on.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // The lib layer is deliberately pure; keep it free of stray `any`.
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  // ADR-0040 §7: the same eight restrictions the structure test enforces,
  // expressed where they are useful while typing — ESLint underlines the import
  // in the editor, the test fails the build. The duplication is deliberate: a
  // rule that only runs in CI is discovered days later, and a rule that only
  // runs in the editor is trivially bypassed by `--no-eslint`.
  //
  // Every pattern is a REGEX against the literal as written, so it is phrased
  // around `../<layer>/` and not around absolute paths.
  {
    files: ["src/shared/**/*.ts", "src/shared/**/*.tsx"],
    ignores: ["src/shared/api/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // #3: the tail of the arrow. `shared/` is imported by every other
              // layer, so an upward edge here inverts the whole tree.
              group: ["**/entities/*", "**/features/*", "**/widgets/*", "**/pages/*", "**/app/*"],
              message:
                "shared/ must not import a higher layer (ADR-0040): lift the rule into entities/ or the mechanism into shared/lib.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/shared/lib/**/*.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              // #2: the claim that this layer is pure was a comment in this very
              // file, checked by nothing. A React import here makes every
              // function in it untestable without a renderer.
              name: "react",
              message:
                "shared/lib is the pure layer: move the hook to shared/hooks (ADR-0040).",
            },
            {
              name: "react-dom",
              message:
                "shared/lib is the pure layer: move the component to shared/ui (ADR-0040).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/entities/**/*.ts", "src/entities/**/*.tsx"],
    // Tests may mount a router: wrapping a component in `MemoryRouter` is how a
    // domain test stays a DOM test. The rule is about production code deciding
    // where a user goes, which is what the `paths` entry below forbids.
    ignores: ["src/entities/**/*.test.ts", "src/entities/**/*.test.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              // #4: a domain rule that reaches for the transport stops being a
              // rule about the domain.
              name: "react-router-dom",
              message:
                "entities/ is the domain layer: navigation belongs to app/router (ADR-0040).",
            },
          ],
          patterns: [
            {
              group: ["**/api/*", "**/hooks/useResource", "**/hooks/useAsyncResource"],
              message:
                "entities/ must not know about transport: read through a hook in features/ (ADR-0040).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/features/**/*.ts", "src/features/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // #5: a feature that imports the shell cannot be reused on
              // another surface.
              group: ["**/widgets/*", "**/pages/*", "**/app/*"],
              message:
                "features/ must not know the shell: lift the block to widgets/ (ADR-0040).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/widgets/**/*.ts", "src/widgets/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // #6: a block of the shell has no business knowing routes.
              group: ["**/pages/*", "**/app/*"],
              message:
                "widgets/ must not know the routes: the shell owns them (ADR-0040).",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/pages/**/*.ts", "src/pages/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // #7: a page that reaches into the assembly cannot be rendered in
              // isolation.
              group: ["**/app/*"],
              message:
                "pages/ must not import the assembly layer (ADR-0040): read through a provider hook.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/app/**/*.ts", "src/app/**/*.tsx"],
    ignores: ["src/app/main.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // #8 inverted: `app/` itself is only reachable from its entry.
              group: ["**/app/*"],
              message:
                "app/ is imported only by app/main.tsx (ADR-0040).",
            },
          ],
        },
      ],
    },
  },
);