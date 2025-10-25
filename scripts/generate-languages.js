#!/usr/bin/env node
// Update src/i18n/locales.json with labels discovered from common/language.json
// and a complete namespaces list inferred from JSON files.

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const LOCALES_ROOT = path.join(REPO_ROOT, 'src', 'i18n');
const LOCALES_FILE = path.join(LOCALES_ROOT, 'locales.json');

function collectJsonFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap(entry => {
    if (entry.name.startsWith('.')) return [];
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) return collectJsonFiles(p);
    if (entry.isFile() && entry.name.endsWith('.json')) return [p];
    return [];
  });
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

function main() {
  if (!fs.existsSync(LOCALES_ROOT)) {
    console.error(`Shared i18n directory not found: ${LOCALES_ROOT}`);
    process.exit(1);
  }

  const localesMeta = fs.existsSync(LOCALES_FILE)
    ? readJson(LOCALES_FILE)
    : { default: 'en-US', locales: {} };

  const localeDirs = fs
    .readdirSync(LOCALES_ROOT)
    .filter(
      d => !d.startsWith('.') && fs.statSync(path.join(LOCALES_ROOT, d)).isDirectory(),
    );

  // Update locale labels from common/language.json if present
  for (const code of localeDirs) {
    const languageFile = path.join(LOCALES_ROOT, code, 'common', 'language.json');
    if (!fs.existsSync(languageFile)) continue;
    const languageData = readJson(languageFile);
    const label = (languageData && languageData.name) || code;
    if (!localesMeta.locales[code]) {
      localesMeta.locales[code] = { label, rtl: false };
    } else {
      localesMeta.locales[code].label = label;
    }
  }

  // Build namespaces set by scanning JSON and honoring __namespace__
  const namespaces = new Set();
  for (const code of localeDirs) {
    const langDir = path.join(LOCALES_ROOT, code);
    for (const filePath of collectJsonFiles(langDir)) {
      const data = readJson(filePath);
      const declared = data && typeof data.__namespace__ === 'string' && data.__namespace__;
      const ns = declared
        ? declared
        : path
            .relative(langDir, filePath)
            .replace(/\\/g, '/')
            .replace(/\.json$/, '')
            .replace(/\//g, '.');
      namespaces.add(ns);
    }
  }

  localesMeta.namespaces = Array.from(namespaces).sort();

  fs.writeFileSync(LOCALES_FILE, JSON.stringify(localesMeta, null, 2) + '\n');
  console.log(`Updated ${LOCALES_FILE} with ${localesMeta.namespaces.length} namespaces.`);
}

main();
