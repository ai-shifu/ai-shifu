import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Test-only dependency: the official Umami v3.4.0 pnpm lock pins isbot 5.2.2.
// Optionally supply an external isbot package directory; never install it here.
const require = createRequire(import.meta.url);
const packageDir = process.argv[2] && path.resolve(process.argv[2]);
const { isbot } = require(packageDir || "isbot");
const { version } = require(
  packageDir ? path.join(packageDir, "package.json") : "isbot/package.json",
);
assert.equal(version, "5.2.2", "Use the target Umami 3.4 isbot dependency");

// Read the producer's literal mapping without importing the Flask application
// or executing its configuration. Backend tests separately verify exact labels.
const producer = fileURLToPath(
  new URL(
    "../src/api/flaskr/service/common/server_analytics.py",
    import.meta.url,
  ),
);
const clients = JSON.parse(
  execFileSync(
    "python3",
    [
      "-c",
      `import ast, json, pathlib, sys
tree = ast.parse(pathlib.Path(sys.argv[1]).read_text())
mapping = next(node.value for node in tree.body if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == '_SKILL_CLIENTS'
        for target in node.targets))
print(json.dumps(ast.literal_eval(mapping)))`,
      producer,
    ],
    { encoding: "utf8" },
  ),
);
assert.equal(Object.keys(clients).length, 9);
for (const [agent, [, uaName]] of Object.entries(clients)) {
  const ua = `Mozilla/5.0 AI-Shifu-CLI/1.0 (${uaName})`;
  assert.equal(isbot(ua), false, `${agent} must pass the collector bot check`);
}
assert.equal(
  isbot("Mozilla/5.0 AI-Shifu-CLI/1.0 (Grok-Bot)"),
  true,
  "Grok-Bot is an intentional negative control",
);
console.log(`Skill client UAs: 9 accepted, Grok-Bot filtered (isbot ${version}).`);
