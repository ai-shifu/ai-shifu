/* eslint-disable @typescript-eslint/no-require-imports -- The test loads the zero-dependency CommonJS migration CLI directly. */
const {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const {
  LOCAL_ENV_FILENAMES,
  migrateLegacyFrontendEnv,
} = require('../../scripts/migrate-legacy-frontend-env');

describe('legacy frontend environment migration', () => {
  let repoRoot;

  beforeEach(() => {
    repoRoot = mkdtempSync(path.join(os.tmpdir(), 'frontend-env-migration-'));
    mkdirSync(path.join(repoRoot, 'src', 'web'), { recursive: true });
  });

  afterEach(() => {
    rmSync(repoRoot, { recursive: true, force: true });
  });

  function writeEnv(frontendDirectory, filename, content, mode = 0o600) {
    const filePath = path.join(repoRoot, 'src', frontendDirectory, filename);
    mkdirSync(path.dirname(filePath), { recursive: true });
    writeFileSync(filePath, content);
    chmodSync(filePath, mode);
    return filePath;
  }

  it('copies every supported local env file and preserves permissions', () => {
    for (const filename of LOCAL_ENV_FILENAMES) {
      writeEnv('cook-web', filename, `SOURCE=${filename}\n`, 0o640);
    }
    const messages = [];

    const migrated = migrateLegacyFrontendEnv({
      repoRoot,
      logger: message => messages.push(message),
    });

    expect(migrated).toEqual(LOCAL_ENV_FILENAMES);
    for (const filename of LOCAL_ENV_FILENAMES) {
      const targetPath = path.join(repoRoot, 'src', 'web', filename);
      expect(readFileSync(targetPath, 'utf8')).toBe(`SOURCE=${filename}\n`);
      expect(statSync(targetPath).mode & 0o777).toBe(0o640);
    }
    expect(messages).toHaveLength(LOCAL_ENV_FILENAMES.length);
    expect(messages[0]).toContain('[frontend-env-migration] copied');
    expect(messages[0]).toContain('kept the source file for rollback');

    expect(migrateLegacyFrontendEnv({ repoRoot, logger: jest.fn() })).toEqual(
      [],
    );
    expect(
      readFileSync(path.join(repoRoot, 'src', 'cook-web', '.env'), 'utf8'),
    ).toBe('SOURCE=.env\n');
  });

  it('keeps the entire new-path configuration set when any env file exists', () => {
    writeEnv('cook-web', '.env.local', 'SOURCE=legacy\n');
    writeEnv('web', '.env', 'SOURCE=current\n');

    const migrated = migrateLegacyFrontendEnv({
      repoRoot,
      logger: jest.fn(),
    });

    expect(migrated).toEqual([]);
    expect(
      readFileSync(path.join(repoRoot, 'src', 'web', '.env'), 'utf8'),
    ).toBe('SOURCE=current\n');
    expect(() =>
      readFileSync(path.join(repoRoot, 'src', 'web', '.env.local'), 'utf8'),
    ).toThrow();
  });

  it('uses one source configuration set without mixing in later sources', () => {
    const currentSource = path.join(repoRoot, 'source', 'src', 'web');
    const legacySource = path.join(repoRoot, 'source', 'src', 'cook-web');
    const target = path.join(repoRoot, 'worktree', 'src', 'web');
    mkdirSync(currentSource, { recursive: true });
    mkdirSync(legacySource, { recursive: true });
    mkdirSync(target, { recursive: true });
    writeFileSync(path.join(currentSource, '.env'), 'SOURCE=current\n');
    writeFileSync(path.join(legacySource, '.env'), 'SOURCE=legacy\n');
    writeFileSync(path.join(legacySource, '.env.local'), 'LOCAL=legacy\n');

    migrateLegacyFrontendEnv({
      repoRoot,
      sourceFrontendRoots: [currentSource, legacySource],
      targetFrontendRoot: target,
      logger: jest.fn(),
    });

    expect(readFileSync(path.join(target, '.env'), 'utf8')).toBe(
      'SOURCE=current\n',
    );
    expect(() =>
      readFileSync(path.join(target, '.env.local'), 'utf8'),
    ).toThrow();
  });

  it('falls back to the legacy source when the current source has no env set', () => {
    const currentSource = path.join(repoRoot, 'source', 'src', 'web');
    const legacySource = path.join(repoRoot, 'source', 'src', 'cook-web');
    const target = path.join(repoRoot, 'worktree', 'src', 'web');
    mkdirSync(currentSource, { recursive: true });
    mkdirSync(legacySource, { recursive: true });
    mkdirSync(target, { recursive: true });
    writeFileSync(path.join(legacySource, '.env.local'), 'LOCAL=legacy\n');

    const migrated = migrateLegacyFrontendEnv({
      repoRoot,
      sourceFrontendRoots: [currentSource, legacySource],
      targetFrontendRoot: target,
      logger: jest.fn(),
    });

    expect(migrated).toEqual(['.env.local']);
    expect(readFileSync(path.join(target, '.env.local'), 'utf8')).toBe(
      'LOCAL=legacy\n',
    );
  });

  it('does not treat .env.example as runtime configuration', () => {
    writeEnv('cook-web', '.env.example', 'EXAMPLE=true\n');

    expect(migrateLegacyFrontendEnv({ repoRoot, logger: jest.fn() })).toEqual(
      [],
    );
    expect(existsSync(path.join(repoRoot, 'src', 'web', '.env.example'))).toBe(
      false,
    );
  });

  it('treats a dangling target symlink as an existing configuration set', () => {
    writeEnv('cook-web', '.env', 'SOURCE=legacy\n');
    const targetPath = path.join(repoRoot, 'src', 'web', '.env.local');
    symlinkSync('missing-local-env', targetPath);

    expect(migrateLegacyFrontendEnv({ repoRoot, logger: jest.fn() })).toEqual(
      [],
    );
    expect(existsSync(path.join(repoRoot, 'src', 'web', '.env'))).toBe(false);
    expect(lstatSync(targetPath).isSymbolicLink()).toBe(true);
  });

  it('explains how to replace legacy dependencies without migrating them', () => {
    mkdirSync(path.join(repoRoot, 'src', 'cook-web', 'node_modules'), {
      recursive: true,
    });
    const messages = [];

    migrateLegacyFrontendEnv({
      repoRoot,
      logger: message => messages.push(message),
    });

    expect(messages).toEqual([
      expect.stringContaining('run "cd src/web && npm ci"'),
    ]);
    expect(existsSync(path.join(repoRoot, 'src', 'web', 'node_modules'))).toBe(
      false,
    );
  });
});
