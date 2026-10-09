import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { resolveAppBuildMetadata } from './build-metadata';

describe('frontend build metadata', () => {
  let appDirectory: string;
  const markerSha = 'a'.repeat(40);

  beforeEach(() => {
    appDirectory = mkdtempSync(path.join(tmpdir(), 'ai-shifu-build-metadata-'));
    writeFileSync(
      path.join(appDirectory, 'package.json'),
      JSON.stringify({ version: '9.8.7' }),
    );
  });

  afterEach(() => {
    rmSync(appDirectory, { recursive: true, force: true });
  });

  it('uses the checked-out commit ahead of a stale generated marker', () => {
    execFileSync('git', ['init', '--quiet'], { cwd: appDirectory });
    execFileSync(
      'git',
      [
        '-c',
        'user.name=Build metadata test',
        '-c',
        'user.email=build-metadata@example.test',
        '-c',
        'commit.gpgsign=false',
        'commit',
        '--allow-empty',
        '--quiet',
        '-m',
        'fixture',
      ],
      { cwd: appDirectory },
    );
    const checkedOutSha = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: appDirectory,
      encoding: 'utf8',
    }).trim();
    writeFileSync(path.join(appDirectory, '.app-build-sha'), markerSha);

    expect(resolveAppBuildMetadata(appDirectory)).toEqual({
      appVersion: '9.8.7',
      appBuildSha: checkedOutSha,
    });
  });

  it('reads and normalizes the generated marker without a Git checkout', () => {
    writeFileSync(
      path.join(appDirectory, '.app-build-sha'),
      ` ${markerSha.toUpperCase()}\n`,
    );

    expect(resolveAppBuildMetadata(appDirectory)).toEqual({
      appVersion: '9.8.7',
      appBuildSha: markerSha,
    });
  });

  it.each(['', 'abcdef0', `${markerSha}extra`, 'g'.repeat(40)])(
    'omits an invalid build marker: %s',
    marker => {
      writeFileSync(path.join(appDirectory, '.app-build-sha'), marker);

      expect(resolveAppBuildMetadata(appDirectory)).toEqual({
        appVersion: '9.8.7',
        appBuildSha: '',
      });
    },
  );

  it('keeps the package release version when build metadata is unavailable', () => {
    expect(resolveAppBuildMetadata(appDirectory)).toEqual({
      appVersion: '9.8.7',
      appBuildSha: '',
    });
  });
});
