const fs = require('fs');
const path = require('path');

/**
 * Recursively collects all JavaScript and TypeScript source files under a directory, excluding 'local' and 'assets' subdirectories.
 *
 * @param {string} dir - The root directory to search.
 * @param {string[]} [files=[]] - Accumulator for file paths; used internally during recursion.
 * @returns {string[]} An array of absolute file paths for all found .js, .jsx, .ts, and .tsx files.
 */
function getAllFiles(dir, files = []) {
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
}

/**
 * Extracts translation keys from a file matching the pattern t('namespace.key').
 *
 * Scans the specified file for occurrences of translation function calls and returns all found keys in "namespace.key" format.
 *
 * @param {string} filePath - Path to the source file to scan.
 * @returns {string[]} Array of extracted translation keys.
 */
function extractKeysFromFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const regex = /t\('([a-zA-Z0-9_]+)\.([a-zA-Z0-9_.-]+)'\)/g;
  let match, keys = [];
  while ((match = regex.exec(content)) !== null) {
    keys.push(match[1] + '.' + match[2]);
  }
  return keys;
}

/**
 * Inserts a value into a nested object structure based on a dot-separated key path.
 *
 * Creates nested objects as needed for each segment of the key, and sets the value only if the final key does not already exist.
 *
 * @param {object} obj - The object to modify.
 * @param {string} key - Dot-separated path specifying where to insert the value.
 * @param {*} value - The value to set at the specified path.
 */
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

/**
 * Constructs a nested JSON object from an array of dot-separated keys, assigning each leaf node the specified value.
 *
 * @param {string[]} keys - Array of translation keys in dot notation (e.g., "namespace.key").
 * @param {string} langMark - Value to assign to each leaf node, typically indicating the locale.
 * @returns {Object} A nested object representing the translation keys with each leaf set to {@link langMark}.
 */
function buildNestedJson(keys, langMark) {
  const result = {};
  keys.forEach(key => setNested(result, key, langMark));
  return result;
}

/**
 * Recursively merges properties from the patch object into the base object, adding missing keys without overwriting existing values.
 *
 * For nested objects, properties are merged deeply. Non-object values from patch are only set if the key does not already exist in base.
 *
 * @param {Object} base - The target object to merge into.
 * @param {Object} patch - The source object containing properties to add.
 * @returns {Object} The merged base object.
 */
function mergeJson(base, patch) {
  for (const k in patch) {
    if (typeof patch[k] === 'object' && patch[k] !== null && !Array.isArray(patch[k])) {
      if (!base[k]) base[k] = {};
      mergeJson(base[k], patch[k]);
    } else {
      if (!(k in base)) base[k] = patch[k];
    }
  }
  return base;
}

const ROOT_DIR = path.join(__dirname, '..'); // src/cook-web/src/
const LOCALE_DIR = path.join(ROOT_DIR, '../public/locales');

const files = getAllFiles(ROOT_DIR);
const allKeys = Array.from(new Set(files.flatMap(extractKeysFromFile)));

fs.readdirSync(LOCALE_DIR).forEach(file => {
  if (file.endsWith('.json') &&  file !== 'languages.json') {
    const langFile = path.join(LOCALE_DIR, file);
    const langMark = `@${file}`;
    let baseJson = {};
    if (fs.existsSync(langFile)) {
      baseJson = JSON.parse(fs.readFileSync(langFile, 'utf8'));
    }
    const patchJson = buildNestedJson(allKeys, langMark);
    const merged = mergeJson(baseJson, patchJson);
    fs.writeFileSync(langFile, JSON.stringify(merged, null, 2), 'utf8');
    console.log(`${file} updated. ${allKeys.length} keys found.`);
  }
});
