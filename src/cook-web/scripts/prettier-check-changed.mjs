#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import path from 'node:path';

const COOK_WEB_PREFIX = 'src/cook-web/';
const ZERO_SHA = /^0{40}$/;

function fail(message) {
  console.error(message);
  process.exit(1);
}

function parseArgs(argv) {
  const options = {
    base: process.env.PRETTIER_BASE_SHA,
    head: process.env.PRETTIER_HEAD_SHA || 'HEAD',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--base') {
      options.base = argv[index + 1];
      index += 1;
    } else if (arg === '--head') {
      options.head = argv[index + 1];
      index += 1;
    } else {
      fail(`Unknown argument: ${arg}`);
    }
  }

  if (!options.head) {
    fail('Missing head ref. Pass --head or set PRETTIER_HEAD_SHA.');
  }

  return options;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: 'utf8',
    ...options,
  });

  if (result.error) {
    throw result.error;
  }

  return result;
}

function git(args, cwd, options = {}) {
  return run('git', args, { cwd, ...options });
}

function gitOutput(args, cwd) {
  const result = git(args, cwd);
  if (result.status !== 0) {
    fail(result.stderr.trim() || `git ${args.join(' ')} failed`);
  }
  return result.stdout;
}

function commitExists(ref, repoRoot) {
  const result = git(['rev-parse', '--verify', `${ref}^{commit}`], repoRoot, {
    stdio: 'ignore',
  });
  return result.status === 0;
}

function resolveBaseRef(base, head, repoRoot) {
  if (base && !ZERO_SHA.test(base)) {
    if (!commitExists(base, repoRoot)) {
      fail(`Base ref is not available in this checkout: ${base}`);
    }
    return base;
  }

  const parent = `${head}^`;
  if (commitExists(parent, repoRoot)) {
    return parent;
  }

  return null;
}

function readChangedCookWebFiles(repoRoot, base, head) {
  const diffTarget = base ? [`${base}...${head}`] : [head];
  const command = base ? 'diff' : 'ls-tree';
  const args = base
    ? [
        command,
        '--name-only',
        '--diff-filter=ACMR',
        '-z',
        ...diffTarget,
        '--',
        'src/cook-web',
      ]
    : [command, '-r', '--name-only', '-z', ...diffTarget, '--', 'src/cook-web'];

  const output = gitOutput(args, repoRoot);
  return output
    .split('\0')
    .filter(Boolean)
    .filter(file => file.startsWith(COOK_WEB_PREFIX))
    .map(file => file.slice(COOK_WEB_PREFIX.length));
}

function runPrettier(cookWebRoot, files) {
  if (files.length === 0) {
    console.log('No changed Cook Web files to check.');
    return 0;
  }

  console.log(
    `Checking Prettier formatting for ${files.length} changed Cook Web file(s).`,
  );
  for (const file of files) {
    console.log(`  ${file}`);
  }

  const result = run(
    'npx',
    ['prettier', '--check', '--ignore-unknown', '--', ...files],
    {
      cwd: cookWebRoot,
      stdio: 'inherit',
    },
  );

  if (result.signal) {
    console.error(`Prettier exited after signal ${result.signal}.`);
    return 1;
  }

  return result.status ?? 1;
}

const { base, head } = parseArgs(process.argv.slice(2));
const repoRoot = gitOutput(
  ['rev-parse', '--show-toplevel'],
  process.cwd(),
).trim();
const cookWebRoot = path.join(repoRoot, 'src/cook-web');

if (!commitExists(head, repoRoot)) {
  fail(`Head ref is not available in this checkout: ${head}`);
}

const resolvedBase = resolveBaseRef(base, head, repoRoot);
const changedFiles = readChangedCookWebFiles(repoRoot, resolvedBase, head);
process.exit(runPrettier(cookWebRoot, changedFiles));
