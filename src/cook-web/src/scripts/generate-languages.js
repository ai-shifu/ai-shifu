const fs = require('fs'); // eslint-disable-line
const path = require('path'); // eslint-disable-line

const localesRoot = path.join(__dirname, '../../i18n');
const localesFile = path.join(localesRoot, 'locales.json');

const localesMeta = fs.existsSync(localesFile)
  ? JSON.parse(fs.readFileSync(localesFile, 'utf-8'))
  : { default: 'en-US', locales: {} };

const directories = fs
  .readdirSync(localesRoot)
  .filter(
    entry =>
      !entry.startsWith('.') &&
      fs.statSync(path.join(localesRoot, entry)).isDirectory(),
  );

directories.forEach(code => {
  const langFile = path.join(localesRoot, code, 'langName.json');

  if (!fs.existsSync(langFile)) {
    return;
  }

  const label = JSON.parse(fs.readFileSync(langFile, 'utf-8'));

  if (!localesMeta.locales[code]) {
    localesMeta.locales[code] = { label, rtl: false };
  } else {
    localesMeta.locales[code].label = label;
  }
});

const namespaces = new Set();

directories.forEach(code => {
  const langDir = path.join(localesRoot, code);

  fs.readdirSync(langDir)
    .filter(file => file.endsWith('.json') && file !== 'langName.json')
    .forEach(file => namespaces.add(file.replace('.json', '')));
});

localesMeta.namespaces = Array.from(namespaces).sort();

fs.writeFileSync(localesFile, `${JSON.stringify(localesMeta, null, 2)}\n`);
