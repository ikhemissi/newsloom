import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "playwright-report/**", "test-results/**"] },
  ...tseslint.configs.recommended,
  {
    rules: {
      "no-console": "error",
      "no-eval": "error",
      "no-new-func": "error",
      "no-restricted-syntax": [
        "error",
        { selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']", message: "Render text inertly." },
        { selector: "MemberExpression[property.name=/^(innerHTML|outerHTML|insertAdjacentHTML)$/]", message: "Render text inertly." }
      ],
    },
  },
);
