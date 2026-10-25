import { execFileSync } from 'node:child_process';
import path from 'node:path';

it('protects only the installation and local administrator credential pages', () => {
  const output = execFileSync(
    process.execPath,
    [
      '-e',
      `
      const loadConfig = require('next/dist/server/config').default;
      (async () => {
        const config = await loadConfig('phase-production-build', process.cwd());
        process.stdout.write(JSON.stringify(await config.headers()));
      })().catch(error => { console.error(error); process.exitCode = 1; });
      `,
    ],
    { cwd: path.resolve(__dirname, '../..'), encoding: 'utf8' },
  );
  const rows = JSON.parse(output) as Array<{
    source: string;
    headers: Array<{ key: string; value: string }>;
  }>;
  expect(rows.map(row => row.source)).toEqual(['/setup', '/admin-login']);
  for (const row of rows) {
    expect(
      Object.fromEntries(row.headers.map(header => [header.key, header.value])),
    ).toEqual({
      'Content-Security-Policy': "frame-ancestors 'none'",
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      'Cache-Control': 'no-store',
    });
  }
});
