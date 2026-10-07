#!/usr/bin/env node

import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { runInNewContext } from 'node:vm';

// Resolve from the image, even when CI bind-mounts this probe elsewhere.
const appRoot = process.cwd();
const require = createRequire(path.join(appRoot, 'package.json'));
const manifest = JSON.parse(readFileSync(path.join(appRoot, 'package.json')));
const lock = JSON.parse(readFileSync(path.join(appRoot, 'package-lock.json')));

for (const name of Object.keys(manifest.dependencies)) {
  const installed = JSON.parse(
    readFileSync(
      path.join(appRoot, 'node_modules', name, 'package.json'),
      'utf8',
    ),
  );
  assert.equal(
    installed.name,
    name,
    `Production dependency is missing: ${name}`,
  );
  assert.equal(
    installed.version,
    lock.packages[`node_modules/${name}`].version,
    `Production dependency changed version: ${name}`,
  );
}
for (const name of Object.keys(manifest.devDependencies)) {
  if (lock.packages[`node_modules/${name}`]?.dev === true) {
    assert.equal(
      existsSync(path.join(appRoot, 'node_modules', name)),
      false,
      `Development-only dependency remains: ${name}`,
    );
  }
}

const sharp = require('sharp');
const png = await sharp({
  create: {
    width: 2,
    height: 2,
    channels: 3,
    background: { r: 255, g: 0, b: 0 },
  },
})
  .resize(1, 1)
  .png()
  .toBuffer();
const { data, info } = await sharp(png)
  .removeAlpha()
  .raw()
  .toBuffer({ resolveWithObject: true });
assert.equal(info.width, 1);
assert.equal(info.height, 1);
assert.deepEqual([...data], [255, 0, 0]);

let swcPlatform = `${process.platform}-${process.arch}`;
if (process.platform === 'linux') {
  const libc = process.report.getReport().header.glibcVersionRuntime
    ? 'gnu'
    : 'musl';
  swcPlatform += `-${libc}`;
} else if (process.platform === 'win32') {
  swcPlatform += '-msvc';
}
// Load the native binding directly, so a WASM fallback cannot hide a missing binary.
const swc = require(`@next/swc-${swcPlatform}`);
const transformed = swc.transformSync(
  'export const answer: number = 42;',
  false,
  Buffer.from(
    JSON.stringify({
      jsc: { parser: { syntax: 'typescript' } },
      module: { type: 'commonjs' },
    }),
  ),
);
const exports = {};
runInNewContext(transformed.code, { exports });
assert.equal(exports.answer, 42);

const i18nRoot = process.env.I18N_ROOT || path.join(appRoot, 'i18n');
const metadata = JSON.parse(
  readFileSync(path.join(i18nRoot, 'locales.json'), 'utf8'),
);
assert.ok(metadata.locales[metadata.default], 'Default locale is undeclared');
for (const locale of Object.keys(metadata.locales)) {
  const resource = JSON.parse(
    readFileSync(path.join(i18nRoot, locale, 'common', 'core.json'), 'utf8'),
  );
  assert.equal(resource.__namespace__, 'common.core');
}

console.log(
  `Production dependencies passed: ${process.platform}/${process.arch}, Sharp image conversion, native SWC, and ${Object.keys(metadata.locales).length} locales.`,
);
