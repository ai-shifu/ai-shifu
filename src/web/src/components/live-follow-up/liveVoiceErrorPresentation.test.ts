jest.mock('@/lib/request', () => ({ __esModule: true, default: jest.fn() }));
import { LiveFollowUpControlError } from '@/lib/liveVoiceFollowUp';
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
    capacityKeys: [],
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
    for (const namespace of [
      'liveVoiceErrors',
      'liveVoiceErrorStages',
      'liveVoiceCapacityScopes',
    ]) {
      expect(Object.keys(messages[namespace])).toEqual(
        Object.keys(reference[namespace]),
      );
      for (const text of Object.values(messages[namespace]))
        expect(text).toEqual(expect.any(String));
    }
  }
});

it('shows all known capacity scopes once and excludes untrusted response values', () => {
  const error = new LiveFollowUpControlError('capacity_exceeded', 2000, [
    'user_mint_rate',
    'https://secret',
    'user_credentials',
    'user_credentials',
    '__proto__',
  ]);
  expect(error.capacityScopes).toEqual(['user_credentials', 'user_mint_rate']);
  expect(
    liveVoiceErrorPresentation('capacity_exceeded', {
      stage: 'session_create',
      capacityScopes: error.capacityScopes,
    }).capacityKeys,
  ).toEqual([
    'module.chat.liveVoiceCapacityScopes.user_credentials',
    'module.chat.liveVoiceCapacityScopes.user_mint_rate',
  ]);
  expect(
    new LiveFollowUpControlError('response_lost', 0, ['user_credentials'])
      .capacityScopes,
  ).toEqual([]);
});
it.each([undefined, null, 'user_credentials', ['unknown']])(
  'keeps the generic capacity fallback for %j',
  scopes => {
    const error = new LiveFollowUpControlError('capacity_exceeded', 0, scopes);
    const detail = liveVoiceErrorPresentation('capacity_exceeded', {
      stage: 'session_create',
      capacityScopes: error.capacityScopes,
    });
    expect(detail.capacityKeys).toEqual([]);
    expect(detail.messageKey).toBe(
      'module.chat.liveVoiceErrors.capacity_exceeded',
    );
  },
);
