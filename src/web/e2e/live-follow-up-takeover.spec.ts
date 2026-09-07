import { readFileSync } from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import { expect, test } from '@playwright/test';

// Browser control-plane integration: actual production admission and ownership
// modules, native refresh/BroadcastChannel, and a deterministic HTTP provider.
// This does not replace full AskBlock/real-Gemini device acceptance.
const modules: Record<string, string> = {
  'admission.js':
    'src/components/live-follow-up/liveFollowUpSessionAdmission.ts',
  'ownership.js': 'src/components/live-follow-up/liveFollowUpOwnership.ts',
  'liveVoiceFollowUp.js': 'src/lib/liveVoiceFollowUp.ts',
};
const scripts = Object.fromEntries(
  Object.entries(modules).map(([name, file]) => [
    name,
    ts
      .transpileModule(readFileSync(path.resolve(file), 'utf8'), {
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ES2022,
        },
      })
      .outputText.replaceAll(
        '@/lib/liveVoiceFollowUp',
        '/modules/liveVoiceFollowUp.js',
      )
      .replaceAll('@/lib/request', '/modules/request.js'),
  ]),
);

test('refresh and another page take over without waiting for old credentials', async ({
  context,
  page,
}) => {
  let revision: string | null = null;
  let issued = 0;
  let lookups = 0;
  const expires = new Date(Date.now() + 900_000).toISOString();
  await context.route('http://localhost:43127/**', async route => {
    const url = new URL(route.request().url());
    const respond = (body: object) => route.fulfill({ json: body });
    if (url.pathname === '/api/learn/live-follow-up/owner') {
      lookups++;
      return respond({
        operation_status: revision ? 'issued' : 'missing',
        admission_revision: revision,
        rotation_enabled: true,
      });
    }
    if (url.pathname.endsWith('/heartbeat')) {
      const current = url.pathname.includes(`/session/session-${issued}/`);
      return respond(
        current
          ? {}
          : { operation_status: 'rejected', error_code: 'ownership_conflict' },
      );
    }
    if (url.pathname.endsWith('/session')) {
      const input = route.request().postDataJSON();
      expect(input.operation).toBe('takeover');
      if (input.expected_admission_revision !== (revision ?? '')) {
        return respond({
          operation_status: 'rejected',
          request_bid: input.request_bid,
          error_code: 'ownership_conflict',
          rotation_enabled: true,
        });
      }
      issued++;
      revision = `revision-${issued}`;
      return respond({
        session_bid: `session-${issued}`,
        request_bid: input.request_bid,
        admission_revision: revision,
        rotation_enabled: true,
        operation_status: 'issued',
        ephemeral_token: 'auth_tokens/non-secret-test-fixture',
        expires_at: expires,
        expires_in_ms: 900_000,
        ownership_timeout_ms: 10_000,
      });
    }
    if (url.pathname === '/modules/request.js') {
      return route.fulfill({
        contentType: 'text/javascript',
        body: `export default {
        post: async (url, body) => (await fetch(url, { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json()
      };`,
      });
    }
    if (url.pathname.startsWith('/modules/')) {
      return route.fulfill({
        contentType: 'text/javascript',
        body: scripts[url.pathname.split('/').pop()!],
      });
    }
    return route.fulfill({
      contentType: 'text/html',
      body: `<!doctype html><button id="start">Speak</button>
      <output id="state">idle</output><script type="module">
      import { LiveFollowUpSessionAdmission } from '/modules/admission.js';
      import { LiveFollowUpOwnership } from '/modules/ownership.js';
      const admission = new LiveFollowUpSessionAdmission();
      let current = true;
      document.querySelector('#start').onclick = async () => {
        const output = document.querySelector('#state');
        output.textContent = 'connecting';
        try {
          const session = await admission.create('course', 'outline', {
            anchor_element_bid: 'anchor', preview_mode: false, learning_mode: 'read', surface: 'read_content'
          }, () => current);
          const owner = new LiveFollowUpOwnership(session.session_bid, session.admission_revision,
            () => { output.textContent = 'ready'; }, () => { current = false; output.textContent = 'stopped'; });
          await owner.start(session.previous_admission_revision);
        } catch { output.textContent = 'failed'; }
      };
      </script>`,
    });
  });
  await page.goto('http://localhost:43127/');
  expect(lookups).toBe(0);
  await page.getByRole('button', { name: 'Speak' }).click();
  await expect(page.locator('output')).toHaveText('ready');
  expect(issued).toBe(1);
  await page.reload();
  await expect(page.locator('output')).toHaveText('idle');
  expect(issued).toBe(1);
  await page.getByRole('button', { name: 'Speak' }).click();
  await expect(page.locator('output')).toHaveText('ready', { timeout: 5_000 });
  expect(issued).toBe(2);
  expect(Date.parse(expires)).toBeGreaterThan(Date.now());

  const other = await context.newPage();
  await other.goto('http://localhost:43127/');
  expect(issued).toBe(2);
  await other.getByRole('button', { name: 'Speak' }).click();
  await expect(other.locator('output')).toHaveText('ready');
  await expect(page.locator('output')).toHaveText('stopped', {
    timeout: 5_000,
  });
  expect(issued).toBe(3);
});
