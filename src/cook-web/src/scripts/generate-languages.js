const fs = require('fs');
const path = require('path');

const localesDir = path.join(__dirname, '../../public/locales');
const files = fs.readdirSync(localesDir);
const langMap = {};

files.forEach(file => {
  if (file.endsWith('.json')) {
    const code = file.replace('.json', '');
    const content = fs.readFileSync(path.join(localesDir, file), 'utf-8');
    const json = JSON.parse(content);

    langMap[code] = json.langName;
  }
});

fs.writeFileSync(
  path.join(localesDir, 'languages.json'),
  JSON.stringify(langMap, null, 2),
);
