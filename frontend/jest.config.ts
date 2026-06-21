import type { Config } from "jest"
import nextJest from "next/jest.js"

const createJestConfig = nextJest({ dir: "./" })

const config: Config = {
  setupFiles: ["<rootDir>/jest.polyfills.js"],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  testEnvironment: "jest-environment-jsdom",
  testEnvironmentOptions: {
    customExportConditions: ["node", "node-addons"],
  },
  passWithNoTests: true,
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
}

// next/jest sets its own transformIgnorePatterns; override after the fact to
// also transform msw and its ESM dependencies.
const jestConfig = createJestConfig(config)

export default async () => {
  const cfg = await (jestConfig as () => Promise<Config>)()
  return {
    ...cfg,
    transformIgnorePatterns: [
      "node_modules/(?!(msw|@mswjs|rettime|until-async|@open-draft|headers-polyfill|path-to-regexp|react-markdown|remark(-[a-z-]+)?|unified|bail|ccount|character-entities|comma-separated-tokens|decode-named-character-reference|escape-string-regexp|hast-util(-[a-z-]+)?|is-plain-obj|longest-streak|markdown-table|mdast-util(-[a-z-]+)?|micromark(-[a-z-]+)?|property-information|space-separated-tokens|trim-lines|trough|unist-util(-[a-z-]+)?|vfile(-[a-z-]+)?|zwitch)/)",
    ],
  }
}
