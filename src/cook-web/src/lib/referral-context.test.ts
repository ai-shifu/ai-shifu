import {
  buildReferralLoginPayload,
  clearReferralContext,
  normalizeReferralInviteCode,
  readReferralContext,
  saveReferralContext,
} from './referral-context';

describe('referral-context', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test('normalizes invite codes for storage and login payloads', () => {
    expect(normalizeReferralInviteCode(' ab12 cd34 ')).toBe('AB12CD34');

    const saved = saveReferralContext({
      invite_code: ' ab12 cd34 ',
      referral_session_id: 'session-1',
      referral_entry_source: 'manual_code',
    });

    expect(saved).toEqual({
      invite_code: 'AB12CD34',
      referral_session_id: 'session-1',
      referral_entry_source: 'manual_code',
    });
    expect(readReferralContext()).toEqual(saved);
    expect(buildReferralLoginPayload()).toEqual(saved);
  });

  test('clears saved context after successful referral login', () => {
    saveReferralContext({
      invite_code: 'AB12CD34',
      referral_session_id: 'session-1',
      referral_entry_source: 'invite_link',
    });

    clearReferralContext();

    expect(readReferralContext()).toEqual({});
    expect(buildReferralLoginPayload()).toEqual({});
  });
});
