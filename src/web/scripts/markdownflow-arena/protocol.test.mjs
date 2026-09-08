import assert from 'node:assert/strict';
import test from 'node:test';
import { parseRendererOutput, rendererTimeoutMs } from './protocol.mjs';

test('renderer output permits diagnostics before the final nonempty JSON line', () => {
  assert.deepEqual(
    parseRendererOutput('Preparing assets\r\n{"status":"complete"}\r\n \r\n'),
    { status: 'complete' },
  );
  assert.throws(() => parseRendererOutput(''), SyntaxError);
  assert.throws(
    () => parseRendererOutput('{"status":"complete"}\nnoise'),
    SyntaxError,
  );
});

test('renderer deadline matches the pipeline timeout range and default', () => {
  assert.equal(rendererTimeoutMs(), 300000);
  assert.equal(rendererTimeoutMs('30'), 30000);
  assert.equal(rendererTimeoutMs('1200'), 1200000);
  for (const invalid of ['29', '1201', '30.5', 'NaN', 'Infinity', '']) {
    assert.throws(() => rendererTimeoutMs(invalid), {
      code: 'invalid_renderer_timeout',
    });
  }
});
