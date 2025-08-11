/* eslint-disable no-console */
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
    const regex =
      /(?:{)?\s*t\s*\(\s*['"]([a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+)['"]\s*(?:,\s*\{[^}]*\})?\s*\)(?:})?/g;
    let match,
      keys = [];

    while ((match = regex.exec(content)) !== null) {
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
      if (a === 'langName') return -1;
      if (b === 'langName') return 1;

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

    if (key === 'langName' || validKeysSet.has(fullKey)) {
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
const LOCALE_DIR = path.join(ROOT_DIR, '../public/locales');

const files = getAllFiles(ROOT_DIR);
const allKeys = Array.from(new Set(files.flatMap(extractKeysFromFile)));

fs.readdirSync(LOCALE_DIR).forEach(file => {
  if (file.endsWith('.json') && file !== 'languages.json') {
    const langFile = path.join(LOCALE_DIR, file);
    const langMark = `@${file}`;
    let baseJson = {};

    try {
      if (fs.existsSync(langFile)) {
        baseJson = JSON.parse(fs.readFileSync(langFile, 'utf8'));
      }
      const patchJson = buildNestedJson(allKeys, langMark);
      const prunedBaseJson = pruneUnusedKeys(baseJson, allKeys);
      const merged = mergeJson(prunedBaseJson, patchJson);
      const sorted = sortObjectKeys(merged);

      fs.writeFileSync(langFile, JSON.stringify(sorted, null, 2), 'utf8');
    } catch (error) {
      console.error(`${file} update failed. ${error}`);
    }
  }
});
