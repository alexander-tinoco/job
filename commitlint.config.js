export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      ["feat", "fix", "refactor", "test", "docs", "chore", "build", "ci", "perf", "style"],
    ],
    "scope-enum": [
      2,
      "always",
      ["api", "db", "ingest", "ai", "web", "auth", "infra", "docs"],
    ],
    "subject-case": [2, "always", "lower-case"],
    "header-max-length": [2, "always", 72],
    // Title only: no body, no footers, no Co-Authored-By.
    "body-empty": [2, "always"],
    "footer-empty": [2, "always"],
  },
};
