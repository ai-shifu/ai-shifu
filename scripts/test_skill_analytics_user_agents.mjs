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

// Execute only the pure UA formatter and its literal exceptions, without
// importing Flask or application configuration. Read the validated OS catalog.
const producer = fileURLToPath(
  new URL(
    "../src/api/flaskr/service/common/server_analytics.py",
    import.meta.url,
  ),
);
const requestContract = fileURLToPath(
  new URL(
    "../src/api/flaskr/service/common/skill_request_analytics.py",
    import.meta.url,
  ),
);
const samples = JSON.parse(
  execFileSync(
    "python3",
    [
      "-c",
      `import ast, json, pathlib, sys
tree = ast.parse(pathlib.Path(sys.argv[1]).read_text())
selected = [node for node in tree.body
    if (isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
        and target.id == '_CLI_UA_AGENT_NAMES' for target in node.targets))
    or (isinstance(node, ast.FunctionDef) and node.name == '_cli_user_agent')]
assert len(selected) == 2
namespace = {}
exec(compile(ast.Module(body=selected, type_ignores=[]), sys.argv[1], 'exec'), namespace)
contract = ast.parse(pathlib.Path(sys.argv[2]).read_text())
names = next(ast.literal_eval(node.value.args[0]) for node in contract.body
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
        and target.id == 'CALLER_AGENT_NAMES' for target in node.targets))
versions = ['0.0.0', '2.0.0', '2.0.1', '999999.999999.999999']
print(json.dumps([[name, version, namespace['_cli_user_agent'](version, name)]
    for name in sorted(names) for version in versions]))`,
      producer,
      requestContract,
    ],
    { encoding: "utf8" },
  ),
);
assert.equal(new Set(samples.map(([name]) => name)).size, 36);
for (const [name, release, ua] of samples) {
  assert.ok(ua.startsWith(`Mozilla/5.0 AI-Shifu-CLI/${release} (`));
}
const filtered = samples.filter(([, , ua]) => isbot(ua));
assert.deepEqual(
  filtered,
  [],
  "All emitted client UAs must pass the bot check",
);
assert.equal(
  isbot("Mozilla/5.0 AI-Shifu-CLI/2.0.0 (Grok-Bot)"),
  true,
  "Grok-Bot is an intentional negative control",
);
assert.equal(
  isbot("Mozilla/5.0 AI-Shifu-Backend/1.0"),
  false,
  "The shared backend sender UA must pass the bot check",
);
console.log(
  `CLI UAs: ${samples.length} real-version samples and the backend UA accepted; Grok-Bot filtered (isbot ${version}).`,
);
