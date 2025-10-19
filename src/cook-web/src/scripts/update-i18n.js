const fs = require('fs'); // eslint-disable-line
const path = require('path'); // eslint-disable-line

function getAllFiles(dir, files = []) {
  try {
    fs.readdirSync(dir).forEach(file => {
      const fullPath = path.join(dir, file);

      if (fs.statSync(fullPath).isDirectory()) {
        if (!['local', 'assets'].includes(file)) {
          getAllFiles(fullPath, files);
        }
      } else if (/\.(js|jsx|ts|tsx)$/.test(file)) {
        files.push(fullPath);
      }
    });

    return files;
  } catch (error) {
    console.error(`${dir} read failed. ${error}`);

    return [];
  }
}

function extractKeysFromFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    // First normalize the content to handle multiline t() calls
    // Replace newlines within t() calls with spaces
    const normalizedContent = content.replace(/\bt\s*\(\s*\n\s*/g, 't(');

    // Match t() function calls in various contexts including JSX attributes
    // This regex handles: t(`namespace.key`), t(`namespace.key`, {...}), {t(`namespace.key`)}, placeholder={t(`namespace.key`)}, etc.
    const tRegex =
      /\bt\s*\(\s*['"]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"](?:\s*,\s*[^)]+)?\s*\)/g;
    const setErrorRegex =
      /setError\s*\(\s*['"]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"]\s*\)/g;

    let match,
      keys = [];

    // Extract keys from t() calls
    while ((match = tRegex.exec(normalizedContent)) !== null) {
      keys.push(match[1]);
    }

    // Extract keys from setError() calls that use translation keys
    while ((match = setErrorRegex.exec(normalizedContent)) !== null) {
      keys.push(match[1]);
    }

    return keys;
  } catch (error) {
    console.error(`${filePath} read failed. ${error}`);

    return [];
  }
}

function setNested(obj, key, value) {
  const keys = key.split('.');
  let cur = obj;

  keys.forEach((k, idx) => {
    if (idx === keys.length - 1) {
      if (!(k in cur)) cur[k] = value;
    } else {
      if (!(k in cur)) cur[k] = {};
      cur = cur[k];
    }
  });
}

function buildNestedJson(keys, langMark) {
  const result = {};

  keys.forEach(key => setNested(result, key, langMark));

  return result;
}

function mergeJson(base, patch) {
  for (const k in patch) {
    if (
      typeof patch[k] === 'object' &&
      patch[k] !== null &&
      !Array.isArray(patch[k])
    ) {
      if (!base[k]) base[k] = {};
      mergeJson(base[k], patch[k]);
    } else {
      if (!(k in base)) base[k] = patch[k];
    }
  }

  return base;
}

function sortObjectKeys(obj) {
  if (typeof obj !== 'object' || obj === null || Array.isArray(obj)) {
    return obj;
  }

  const sortedObj = {};

  Object.keys(obj)
    .sort((a, b) => {
      if (a === 'common.language.name') return -1;
      if (b === 'common.language.name') return 1;

      return a.localeCompare(b);
    })
    .forEach(key => {
      sortedObj[key] = sortObjectKeys(obj[key]);
    });

  return sortedObj;
}

function pruneUnusedKeys(obj, validKeys, prefix = '') {
  if (typeof obj !== 'object' || obj === null) return obj;
  const result = {};
  const validKeysSet = new Set(validKeys);

  const hasValidChildren = (obj, currentPrefix) => {
    for (const key in obj) {
      const fullKey = currentPrefix ? `${currentPrefix}.${key}` : key;

      if (validKeysSet.has(fullKey)) return true;
      if (typeof obj[key] === 'object' && obj[key] !== null) {
        if (hasValidChildren(obj[key], fullKey)) return true;
      }
    }

    return false;
  };

  for (const key in obj) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (key === 'common.language.name' || validKeysSet.has(fullKey)) {
      if (typeof obj[key] === 'object' && obj[key] !== null) {
        result[key] = pruneUnusedKeys(obj[key], validKeysSet, fullKey);
      } else {
        result[key] = obj[key];
      }
    } else if (typeof obj[key] === 'object' && obj[key] !== null) {
      if (hasValidChildren(obj[key], fullKey)) {
        result[key] = pruneUnusedKeys(obj[key], validKeysSet, fullKey);
      }
    }
  }

  return result;
}

const ROOT_DIR = path.join(__dirname, '..'); // src/cook-web/src/
const LOCALES_ROOT = path.join(ROOT_DIR, '../i18n');

const files = getAllFiles(ROOT_DIR);
const allKeys = Array.from(new Set(files.flatMap(extractKeysFromFile)));

const namespaceMap = new Map();

allKeys.forEach(key => {
  const parts = key.split('.');
  if (parts.length < 2) return;
  const [namespace, ...rest] = parts;
  const subKey = rest.join('.');
  if (!subKey) return;

  if (!namespaceMap.has(namespace)) {
    namespaceMap.set(namespace, new Set());
  }

  namespaceMap.get(namespace).add(subKey);
});

const locales = fs
  .readdirSync(LOCALES_ROOT)
  .filter(
    entry =>
      !entry.startsWith('.') &&
      fs.statSync(path.join(LOCALES_ROOT, entry)).isDirectory(),
  );

locales.forEach(locale => {
  const localeDir = path.join(LOCALES_ROOT, locale);

  namespaceMap.forEach((keysSet, namespace) => {
    const keys = Array.from(keysSet);
    const filePath = path.join(localeDir, `${namespace}.json`);
    const langMark = `@${locale}.${namespace}`;
    let baseJson = {};

    try {
      if (fs.existsSync(filePath)) {
        baseJson = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      }

      const patchJson = buildNestedJson(keys, langMark);
      const prunedBaseJson = pruneUnusedKeys(baseJson, keys);
      const merged = mergeJson(prunedBaseJson, patchJson);
      const sorted = sortObjectKeys(merged);

      fs.mkdirSync(localeDir, { recursive: true });
      fs.writeFileSync(
        filePath,
        `${JSON.stringify(sorted, null, 2)}\n`,
        'utf8',
      );
    } catch (error) {
      console.error(`${locale}/${namespace} update failed. ${error}`);
    }
  });
});
