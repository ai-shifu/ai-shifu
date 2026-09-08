import { liveVoiceErrorPresentation } from './liveVoiceErrorPresentation';
import type { LiveVoiceErrorDiagnostic } from './useLiveVoiceFollowUp';

it('does not display untrusted errors, reasons or invalid close codes', () => {
  const secret = 'wss://provider?key=secret&prompt=private';
  const detail = liveVoiceErrorPresentation(secret, {
    stage: secret,
    reason: secret,
    websocketCloseCode: NaN,
  } as unknown as LiveVoiceErrorDiagnostic);
  expect(detail).toEqual({
    code: 'unknown',
    messageKey: 'module.chat.liveVoiceErrors.unknown',
    stageKey: null,
    closeCode: null,
  });
  expect(JSON.stringify(detail)).not.toContain(secret);
});

it.each([
  'ownership_conflict',
  'stale_request',
  'operation_conflict',
  'admission_unavailable',
  'pending',
  'response_lost',
  'capacity_exceeded',
] as const)('retains the bounded control reason %s', reason => {
  expect(
    liveVoiceErrorPresentation('server_error', {
      stage: 'session_create',
      reason,
    }).code,
  ).toBe(reason);
});

it('provides every error and stage in every supported locale', () => {
  const fs = jest.requireActual<typeof import('fs')>('fs');
  const path = jest.requireActual<typeof import('path')>('path');
  const root = path.resolve(process.cwd(), '../i18n');
  const { locales } = JSON.parse(
    fs.readFileSync(path.join(root, 'locales.json'), 'utf8'),
  );
  const reference = JSON.parse(
    fs.readFileSync(path.join(root, 'en-US/modules/chat.json'), 'utf8'),
  );
  for (const locale of Object.keys(locales)) {
    const messages = JSON.parse(
      fs.readFileSync(path.join(root, locale, 'modules/chat.json'), 'utf8'),
    );
    for (const namespace of ['liveVoiceErrors', 'liveVoiceErrorStages']) {
      expect(Object.keys(messages[namespace])).toEqual(
        Object.keys(reference[namespace]),
      );
      for (const text of Object.values(messages[namespace]))
        expect(text).toEqual(expect.any(String));
    }
  }
});
