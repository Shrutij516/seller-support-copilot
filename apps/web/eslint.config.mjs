import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

// eslint-config-next already registers the jsx-a11y plugin (under a handful of its own
// rules), so this only adds rules, it doesn't re-register the plugin, which flat config
// rejects as a duplicate.
const config = [
  ...nextVitals,
  ...nextTs,
  { rules: jsxA11y.flatConfigs.recommended.rules },
  { ignores: [".next/**", "out/**", "next-env.d.ts"] },
];

export default config;
