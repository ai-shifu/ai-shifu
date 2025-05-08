const fs = require('fs');
const path = require('path');

/**
 * Recursively collects all JavaScript and TypeScript source file paths from a directory, excluding 'local' and 'assets' subdirectories.
 *
 * @param {string} dir - The root directory to search.
 * @param {string[]} [files=[]] - Accumulator for file paths; used internally during recursion.
 * @returns {string[]} An array of absolute file paths with .js, .jsx, .ts, or .tsx extensions found under {@link dir}.
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
 * Extracts translation keys from a file by matching occurrences of the pattern t('namespace.key').
 *
 * @param {string} filePath - Path to the source file to scan for translation keys.
 * @returns {string[]} An array of translation keys found in the file, each in the format 'namespace.key'.
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
 * Sets a value in a nested object structure based on a dot-separated key path, creating intermediate objects as needed.
 *
 * If the final key already exists in the object, its value is not overwritten.
 *
 * @param {Object} obj - The target object to modify.
 * @param {string} key - Dot-separated path specifying where to set the value.
 * @param {*} value - The value to assign at the specified key path.
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
 * Constructs a nested JSON object from an array of dot-separated keys, assigning each key path the specified value.
 *
 * @param {string[]} keys - Array of translation keys in dot notation (e.g., 'namespace.key').
 * @param {string} langMark - Value to assign to each key path in the resulting object.
 * @returns {Object} A nested object representing all key paths with their values set to {@link langMark}.
 */
function buildNestedJson(keys, langMark) {
  const result = {};
  keys.forEach(key => setNested(result, key, langMark));
  return result;
}

/**
 * Recursively merges properties from the {@link patch} object into the {@link base} object without overwriting existing values.
 *
 * For nested objects, properties are merged deeply. Non-object values from {@link patch} are only set if the corresponding key does not exist in {@link base}.
 *
 * @param {Object} base - The target object to merge into.
 * @param {Object} patch - The source object containing properties to merge.
 * @returns {Object} The merged {@link base} object.
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
