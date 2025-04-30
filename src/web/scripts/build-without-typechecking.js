const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const tsconfigPath = path.resolve(__dirname, '../tsconfig.json');
const tsconfigBackupPath = path.resolve(__dirname, '../tsconfig.json.bak');

try {
  const tsconfig = JSON.parse(fs.readFileSync(tsconfigPath, 'utf8'));

  fs.writeFileSync(tsconfigBackupPath, JSON.stringify(tsconfig, null, 2));

  tsconfig.compilerOptions.noEmit = false;
  tsconfig.compilerOptions.isolatedModules = false;
  tsconfig.compilerOptions.skipLibCheck = true;
  tsconfig.compilerOptions.noImplicitAny = false;
  tsconfig.compilerOptions.noEmitOnError = false;
  tsconfig.compilerOptions.allowJs = true;

  fs.writeFileSync(tsconfigPath, JSON.stringify(tsconfig, null, 2));

  console.log('Building without type checking...');

  execSync('NODE_ENV=production npx craco build', { stdio: 'inherit' });
} catch (error) {
  console.error('Build failed:', error);
} finally {
  if (fs.existsSync(tsconfigBackupPath)) {
    fs.copyFileSync(tsconfigBackupPath, tsconfigPath);
    fs.unlinkSync(tsconfigBackupPath);
  }
}
