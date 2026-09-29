import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api-schema.d.ts"] },
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
);