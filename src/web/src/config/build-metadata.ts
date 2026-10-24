import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

interface AppBuildMetadata {
  appVersion: string;
  appBuildSha: string;
}

const normalizeBuildSha = (value: string): string => {
  const sha = value.trim();
  return /^[a-f0-9]{40}$/i.test(sha) ? sha.toLowerCase() : '';
};

// Used only by next.config.ts: metadata is frozen into the frontend build.
export function resolveAppBuildMetadata(
  appDirectory: string,
): AppBuildMetadata {
  const { version } = JSON.parse(
    readFileSync(path.join(appDirectory, 'package.json'), 'utf8'),
  );
  const appVersion = version.trim();

  try {
    const appBuildSha = normalizeBuildSha(
      execFileSync('git', ['rev-parse', 'HEAD'], {
        cwd: appDirectory,
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }),
    );
    if (appBuildSha) {
      return { appVersion, appBuildSha };
    }
  } catch {
    // Docker build contexts intentionally exclude the Git directory.
  }

  try {
    return {
      appVersion,
      appBuildSha: normalizeBuildSha(
        readFileSync(path.join(appDirectory, '.app-build-sha'), 'utf8'),
      ),
    };
  } catch {
    // Source archives without build metadata still expose their release version.
    return { appVersion, appBuildSha: '' };
  }
}
