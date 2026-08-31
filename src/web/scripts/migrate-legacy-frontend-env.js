/* eslint-disable @typescript-eslint/no-require-imports -- This zero-dependency Node CLI must run before frontend transpilation and dependencies are available. */
const {
  closeSync,
  fchmodSync,
  lstatSync,
  openSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeFileSync,
} = require('node:fs');
const path = require('node:path');

const LEGACY_FRONTEND_RELATIVE_PATH = 'src/cook-web';
const CURRENT_FRONTEND_RELATIVE_PATH = 'src/web';
const LOCAL_ENV_FILENAMES = Object.freeze([
  '.env',
  '.env.local',
  '.env.development',
  '.env.development.local',
  '.env.production',
  '.env.production.local',
  '.env.test',
  '.env.test.local',
]);

function formatPath(filePath, repoRoot) {
  const relativePath = path.relative(repoRoot, filePath);
  if (relativePath && !relativePath.startsWith(`..${path.sep}`)) {
    return relativePath.split(path.sep).join('/');
  }
  return filePath;
}

function pathEntryExists(filePath) {
  try {
    lstatSync(filePath);
    return true;
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return false;
    }
    throw error;
  }
}

function regularFileStat(filePath) {
  try {
    const fileStat = statSync(filePath);
    return fileStat.isFile() ? fileStat : null;
  } catch (error) {
    if (error && error.code === 'ENOENT') {
      return null;
    }
    throw error;
  }
}

function cleanUpReservations(reservations) {
  for (const reservation of reservations) {
    if (reservation.fileDescriptor !== null) {
      closeSync(reservation.fileDescriptor);
      reservation.fileDescriptor = null;
    }
  }
  for (const reservation of reservations) {
    try {
      unlinkSync(reservation.targetPath);
    } catch (error) {
      if (!error || error.code !== 'ENOENT') {
        throw error;
      }
    }
  }
}

function warnAboutLegacyDependencies(
  legacyFrontendRoot,
  currentFrontendRoot,
  repoRoot,
  logger,
) {
  const legacyModules = path.join(legacyFrontendRoot, 'node_modules');
  const currentModules = path.join(currentFrontendRoot, 'node_modules');
  if (pathEntryExists(legacyModules) && !pathEntryExists(currentModules)) {
    logger(
      `[frontend-directory-migration] dependencies remain at ${formatPath(legacyModules, repoRoot)}; ` +
        `run "cd ${CURRENT_FRONTEND_RELATIVE_PATH} && npm ci" to install them at the new path.`,
    );
  }
}

function migrateLegacyFrontendEnv({
  repoRoot,
  sourceFrontendRoots,
  targetFrontendRoot,
  logger = console.info,
} = {}) {
  const defaultTarget = path.resolve(__dirname, '..');
  const resolvedTarget =
    targetFrontendRoot ??
    (repoRoot
      ? path.join(repoRoot, CURRENT_FRONTEND_RELATIVE_PATH)
      : defaultTarget);
  const resolvedRepoRoot = repoRoot ?? path.resolve(resolvedTarget, '../..');
  const defaultLegacySource = repoRoot
    ? path.join(repoRoot, LEGACY_FRONTEND_RELATIVE_PATH)
    : path.resolve(resolvedTarget, '..', 'cook-web');
  const resolvedSources = sourceFrontendRoots ?? [defaultLegacySource];
  warnAboutLegacyDependencies(
    defaultLegacySource,
    resolvedTarget,
    resolvedRepoRoot,
    logger,
  );
  const targetHasConfiguration = LOCAL_ENV_FILENAMES.some(filename =>
    pathEntryExists(path.join(resolvedTarget, filename)),
  );
  if (targetHasConfiguration) {
    return [];
  }

  let sourceFiles = [];
  for (const sourceRoot of resolvedSources) {
    const candidateFiles = LOCAL_ENV_FILENAMES.flatMap(filename => {
      const sourcePath = path.join(sourceRoot, filename);
      const sourceStat = regularFileStat(sourcePath);
      return sourceStat ? [{ filename, sourcePath, sourceStat }] : [];
    });
    if (candidateFiles.length > 0) {
      sourceFiles = candidateFiles;
      break;
    }
  }
  if (sourceFiles.length === 0) {
    return [];
  }

  const reservations = [];
  try {
    for (const sourceFile of sourceFiles) {
      const targetPath = path.join(resolvedTarget, sourceFile.filename);
      const fileDescriptor = openSync(
        targetPath,
        'wx',
        sourceFile.sourceStat.mode & 0o777,
      );
      reservations.push({ ...sourceFile, targetPath, fileDescriptor });
    }
  } catch (error) {
    cleanUpReservations(reservations);
    if (error && error.code === 'EEXIST') {
      throw new Error(
        '[frontend-env-migration] refused a partial migration because a new-path env file appeared during the copy',
        { cause: error },
      );
    }
    throw error;
  }

  try {
    for (const reservation of reservations) {
      writeFileSync(
        reservation.fileDescriptor,
        readFileSync(reservation.sourcePath),
      );
      fchmodSync(
        reservation.fileDescriptor,
        reservation.sourceStat.mode & 0o777,
      );
    }
  } catch (error) {
    cleanUpReservations(reservations);
    throw error;
  }

  for (const reservation of reservations) {
    closeSync(reservation.fileDescriptor);
    reservation.fileDescriptor = null;
  }
  for (const reservation of reservations) {
    logger(
      `[frontend-env-migration] copied ${formatPath(reservation.sourcePath, resolvedRepoRoot)} ` +
        `to ${formatPath(reservation.targetPath, resolvedRepoRoot)}; kept the source file for rollback.`,
    );
  }
  return reservations.map(reservation => reservation.filename);
}

function parseCliOptions(argv) {
  const sourceFrontendRoots = [];
  let targetFrontendRoot;

  for (let index = 0; index < argv.length; index += 1) {
    const option = argv[index];
    const value = argv[index + 1];
    if ((option === '--source' || option === '--target') && !value) {
      throw new Error(`${option} requires a directory path`);
    }
    if (option === '--source') {
      sourceFrontendRoots.push(path.resolve(value));
      index += 1;
    } else if (option === '--target') {
      targetFrontendRoot = path.resolve(value);
      index += 1;
    } else {
      throw new Error(`unknown option: ${option}`);
    }
  }

  return {
    ...(sourceFrontendRoots.length > 0 ? { sourceFrontendRoots } : {}),
    ...(targetFrontendRoot ? { targetFrontendRoot } : {}),
  };
}

if (require.main === module) {
  migrateLegacyFrontendEnv(parseCliOptions(process.argv.slice(2)));
}

module.exports = {
  LOCAL_ENV_FILENAMES,
  migrateLegacyFrontendEnv,
  parseCliOptions,
};
