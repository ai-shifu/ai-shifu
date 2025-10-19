const fs = require('fs'); // eslint-disable-line
const path = require('path'); // eslint-disable-line

const localesRoot = path.join(__dirname, '../../i18n');
const localesFile = path.join(localesRoot, 'locales.json');

const localesMeta = fs.existsSync(localesFile)
  ? JSON.parse(fs.readFileSync(localesFile, 'utf-8'))
  : { default: 'en-US', locales: {} };

const collectJsonFiles = dir => {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap(entry => {
    if (entry.name.startsWith('.')) {
      return [];
    }
    const entryPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return collectJsonFiles(entryPath);
    }
    if (entry.isFile() && entry.name.endsWith('.json')) {
      return [entryPath];
    }
    return [];
  });
};

const readJson = filePath => JSON.parse(fs.readFileSync(filePath, 'utf-8'));

const directories = fs
  .readdirSync(localesRoot)
  .filter(
    entry =>
      !entry.startsWith('.') &&
      fs.statSync(path.join(localesRoot, entry)).isDirectory(),
  );

directories.forEach(code => {
  const languageFile = path.join(localesRoot, code, 'common', 'language.json');
  if (!fs.existsSync(languageFile)) {
    return;
  }

  const languageData = readJson(languageFile);
  const label = languageData?.name ?? code;

  if (!localesMeta.locales[code]) {
    localesMeta.locales[code] = { label, rtl: false };
  } else {
    localesMeta.locales[code].label = label;
  }
});

const namespaces = new Set();

directories.forEach(code => {
  const langDir = path.join(localesRoot, code);
  collectJsonFiles(langDir).forEach(filePath => {
    const data = readJson(filePath);
    const namespace =
      typeof data.__namespace__ === 'string' && data.__namespace__
        ? data.__namespace__
        : path
            .relative(langDir, filePath)
            .replace(/\\/g, '/')
            .replace(/\.json$/, '')
            .replace(/\//g, '.');
    namespaces.add(namespace);
  });
});

localesMeta.namespaces = Array.from(namespaces).sort();

fs.writeFileSync(localesFile, `${JSON.stringify(localesMeta, null, 2)}\n`);
