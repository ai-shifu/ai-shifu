#!/usr/bin/env node
// Scan Cook Web source for i18n key usages and update src/i18n/<locale>/<namespace>.json
// with placeholder entries for missing keys. Also prunes unused keys.

const fs = require('fs');
const path = require('path');

function getAllFiles(dir, files = []) {
  try {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (!['local', 'assets', 'public', '.next', 'node_modules'].includes(entry.name)) {
          getAllFiles(fullPath, files);
        }
      } else if (/\.(js|jsx|ts|tsx)$/.test(entry.name)) {
        files.push(fullPath);
      }
    }
  } catch (err) {
    console.error(`${dir} read failed. ${err}`);
  }
  return files;
}

function extractKeysFromFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const normalized = content.replace(/\bt\s*\(\s*\n\s*/g, 't(');
    const tRegex = /\bt\s*\(\s*['"]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"](?:\s*,\s*[^)]+)?\s*\)/g;
    const setErrorRegex = /setError\s*\(\s*['"]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"]\s*\)/g;
    const keys = [];
    let match;
    while ((match = tRegex.exec(normalized)) !== null) keys.push(match[1]);
    while ((match = setErrorRegex.exec(normalized)) !== null) keys.push(match[1]);
    return keys;
  } catch (err) {
    console.error(`${filePath} parse failed. ${err}`);
    return [];
  }
}

function buildNestedJson(keys, placeholder) {
  const obj = {};
  for (const key of keys) {
    const parts = key.split('.');
    if (parts.length < 2) continue;
    const [namespace, ...rest] = parts;
    if (rest.length === 0) continue;
    let cur = obj;
    for (let i = 0; i < rest.length - 1; i++) {
      const seg = rest[i];
      if (!cur[seg]) cur[seg] = {};
      cur = cur[seg];
    }
    const leaf = rest[rest.length - 1];
    if (!cur[leaf]) cur[leaf] = placeholder;
  }
  return obj;
}

function mergeJson(base, patch) {
  for (const k of Object.keys(patch)) {
    if (patch[k] && typeof patch[k] === 'object' && !Array.isArray(patch[k])) {
      if (!base[k]) base[k] = {};
      mergeJson(base[k], patch[k]);
    } else {
      if (!(k in base)) base[k] = patch[k];
    }
  }
  return base;
}

function sortObjectKeys(obj) {
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) return obj;
  const out = {};
  for (const k of Object.keys(obj).sort((a, b) => a.localeCompare(b))) {
    out[k] = sortObjectKeys(obj[k]);
  }
  return out;
}

function pruneUnusedKeys(obj, validKeys, prefix = '') {
  if (typeof obj !== 'object' || obj === null) return obj;
  const res = {};
  const set = new Set(validKeys);
  const hasValidChildren = (node, pref) => {
    for (const k of Object.keys(node)) {
      const full = pref ? `${pref}.${k}` : k;
      if (set.has(full)) return true;
      if (node[k] && typeof node[k] === 'object') {
        if (hasValidChildren(node[k], full)) return true;
      }
    }
    return false;
  };
  for (const k of Object.keys(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (set.has(full) || k === 'common' || k === 'component' || k === 'module' || k === 'server') {
      if (obj[k] && typeof obj[k] === 'object') res[k] = pruneUnusedKeys(obj[k], set, full);
      else res[k] = obj[k];
    } else if (obj[k] && typeof obj[k] === 'object') {
      if (hasValidChildren(obj[k], full)) res[k] = pruneUnusedKeys(obj[k], set, full);
    }
  }
  return res;
}

function main() {
  const REPO_ROOT = path.resolve(__dirname, '..');
  const COOK_SRC = path.join(REPO_ROOT, 'src', 'cook-web', 'src');
  const LOCALES_ROOT = path.join(REPO_ROOT, 'src', 'i18n');

  if (!fs.existsSync(COOK_SRC)) {
    console.error(`Cook Web source not found: ${COOK_SRC}`);
    process.exit(1);
  }
  if (!fs.existsSync(LOCALES_ROOT)) {
    console.error(`Shared i18n directory not found: ${LOCALES_ROOT}`);
    process.exit(1);
  }

  const files = getAllFiles(COOK_SRC);
  const allKeys = Array.from(new Set(files.flatMap(extractKeysFromFile)));

  const namespaceMap = new Map();
  for (const key of allKeys) {
    const parts = key.split('.');
    if (parts.length < 2) continue;
    const [namespace, ...rest] = parts;
    const subKey = rest.join('.');
    if (!subKey) continue;
    if (!namespaceMap.has(namespace)) namespaceMap.set(namespace, new Set());
    namespaceMap.get(namespace).add(subKey);
  }

  const locales = fs
    .readdirSync(LOCALES_ROOT)
    .filter(d => !d.startsWith('.') && fs.statSync(path.join(LOCALES_ROOT, d)).isDirectory());

  for (const locale of locales) {
    const localeDir = path.join(LOCALES_ROOT, locale);
    for (const [namespace, keysSet] of namespaceMap.entries()) {
      const keys = Array.from(keysSet);
      const filePath = path.join(localeDir, `${namespace}.json`);
      const mark = `@${locale}.${namespace}`;
      let baseJson = {};
      if (fs.existsSync(filePath)) {
        try {
          baseJson = JSON.parse(fs.readFileSync(filePath, 'utf8'));
        } catch (e) {
          console.error(`Failed to parse ${filePath}: ${e}`);
        }
      }
      const patch = buildNestedJson(keys, mark);
      const pruned = pruneUnusedKeys(baseJson, keys);
      const merged = mergeJson(pruned, patch);
      const sorted = sortObjectKeys(merged);
      fs.mkdirSync(path.dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, JSON.stringify(sorted, null, 2) + '\n', 'utf8');
    }
  }
  console.log('Updated i18n files based on usage in Cook Web.');
}

main();
