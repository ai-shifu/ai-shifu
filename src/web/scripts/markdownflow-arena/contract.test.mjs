import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  normalizeArtifact,
  isAllowedAsset,
  isPublicAddress,
  classifyError,
} from './contract.mjs';

test('passes only visual fields and removes identity, audio, and credentials', () => {
  const normalized = normalizeArtifact({
    content: '# Hello',
    artifact_id: 'model-secret',
    metadata: { model: 'model-secret', api_key: 'secret' },
    elements: [
      {
        content: '# Hello',
        type: 'text',
        is_marker: true,
        is_new: true,
        is_speakable: true,
        audio_url: 'https://private.example/secret',
        element_bid: 'model-secret',
        user_input: 'private',
      },
    ],
  });
  assert.equal(normalized.mode, 'slides');
  assert.equal(normalized.stepCount, 1);
  assert.equal(normalized.elements[0].is_new, true);
  assert.equal(normalized.elements[0].is_speakable, false);
  assert.equal(JSON.stringify(normalized).includes('secret'), false);
  assert.equal(JSON.stringify(normalized).includes('private'), false);
});

test('rejects empty artifacts and excessive slide counts', () => {
  assert.throws(() => normalizeArtifact({ content: ' ' }));
  assert.throws(() =>
    normalizeArtifact({ content: '# Hi', elements: [{ content: {} }] }),
  );
  assert.throws(() =>
    normalizeArtifact({
      content: '# Hi',
      elements: Array.from({ length: 121 }, () => ({
        content: '# Hi',
        is_marker: true,
      })),
    }),
  );
  assert.equal(normalizeArtifact({ content: '# Hi' }).mode, 'reading');
});

test('adapts production ElementDTO types to the Slide component contract', () => {
  const normalized = normalizeArtifact({
    content: 'Production output',
    elements: [
      { content: '<div>Slide</div>', element_type: 'html', is_marker: true },
      { content: '<svg/>', element_type: 'svg', is_marker: true },
      { content: 'Speech', element_type: 'text', is_marker: false },
    ],
  });
  assert.deepEqual(
    normalized.elements.map(element => element.type),
    ['html', 'svg', 'text'],
  );
  assert.equal(normalized.stepCount, 2);
});

test('external access is restricted to explicit HTTPS asset hosts and GET', () => {
  const request = (url, type = 'image', method = 'GET') => ({
    url: () => url,
    resourceType: () => type,
    method: () => method,
  });
  const hosts = new Set(['cdn.example']);
  assert.equal(
    isAllowedAsset(request('https://cdn.example/a.png'), hosts),
    true,
  );
  for (const url of [
    'http://cdn.example/a',
    'https://cdn.example:444/a',
    'https://user:pass@cdn.example/a',
    'https://localhost/a',
    'file:///etc/passwd',
  ]) {
    assert.equal(isAllowedAsset(request(url), hosts), false);
  }
  assert.equal(
    isAllowedAsset(request('https://cdn.example/a', 'fetch'), hosts),
    false,
  );
  assert.equal(
    isAllowedAsset(request('https://cdn.example/a', 'image', 'POST'), hosts),
    false,
  );
});

test('private destinations and raw errors cannot cross the renderer boundary', () => {
  for (const address of [
    '127.0.0.1',
    '10.2.3.4',
    '172.16.1.2',
    '192.168.1.1',
    '169.254.169.254',
    '::1',
    '::ffff:127.0.0.1',
    'fc00::1',
    'fe80::1',
  ]) {
    assert.equal(isPublicAddress(address), false);
  }
  assert.equal(isPublicAddress('8.8.8.8'), true);
  assert.equal(isPublicAddress('2606:4700:4700::1111'), true);
  assert.equal(classifyError(new Error('model secret')), 'render_failed');
});
