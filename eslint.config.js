import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import prettier from "eslint-config-prettier";

// Flat config (ESLint 9+). Composes @eslint/js + typescript-eslint + react-hooks
// recommended + react-refresh, with eslint-config-prettier last so it can switch
// off any stylistic rules Prettier already owns.
export default tseslint.config(
  {
    ignores: [
      "dist",
      "src-tauri",
      "engine",
      "node_modules",
      // sibling worktrees here carry their own tsconfig (breaks typescript-eslint)
      ".claude",
      "**/*.config.{js,ts}",
      "src/vite-env.d.ts",
    ],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    rules: {
      // The point of this config: keep the classic Hooks safety rules on, with
      // exhaustive-deps escalated to an error so missing deps fail lint.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",

      // react-hooks v7 also ships the experimental React Compiler rule set. We
      // don't run the compiler, and these fire on deliberate, working React 18
      // patterns (e.g. assigning a ref during render to read the latest value in
      // an async callback, syncing state inside an effect). Turning them off
      // keeps lint focused on real bugs without rewriting behavior that works.
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/immutability": "off",
      "react-hooks/purity": "off",
      "react-hooks/static-components": "off",
      "react-hooks/use-memo": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/set-state-in-render": "off",
      "react-hooks/globals": "off",
      "react-hooks/error-boundaries": "off",
      "react-hooks/incompatible-library": "off",
      "react-hooks/gating": "off",
      "react-hooks/config": "off",
      "react-hooks/unsupported-syntax": "off",
    },
  },
  prettier,
);
