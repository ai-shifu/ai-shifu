import type {
  ReferralEntrySource,
  ReferralLoginMetadata,
} from '@/types/referral';

const REFERRAL_CONTEXT_STORAGE_KEY = 'ai-shifu:referral-context:v1';

type StoredReferralContext = {
  invite_code: string;
  referral_session_id: string;
  referral_entry_source: ReferralEntrySource;
  updated_at: number;
};

const isBrowser = () => typeof window !== 'undefined';

const createSessionId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `ref_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`;
};

export const normalizeReferralInviteCode = (value: unknown) =>
  String(value || '')
    .trim()
    .replace(/\s+/g, '')
    .toUpperCase()
    .slice(0, 32);

const isReferralEntrySource = (value: unknown): value is ReferralEntrySource =>
  value === 'invite_link' || value === 'manual_code';

export const readReferralContext = (): ReferralLoginMetadata => {
  if (!isBrowser()) {
    return {};
  }
  try {
    const rawValue = window.localStorage.getItem(REFERRAL_CONTEXT_STORAGE_KEY);
    if (!rawValue) {
      return {};
    }
    const parsed = JSON.parse(rawValue) as Partial<StoredReferralContext>;
    const inviteCode = normalizeReferralInviteCode(parsed.invite_code);
    if (!inviteCode) {
      return {};
    }
    const sessionId = String(parsed.referral_session_id || '').trim();
    return {
      invite_code: inviteCode,
      referral_session_id: sessionId || createSessionId(),
      referral_entry_source: isReferralEntrySource(parsed.referral_entry_source)
        ? parsed.referral_entry_source
        : 'invite_link',
    };
  } catch {
    return {};
  }
};

export const saveReferralContext = ({
  invite_code,
  referral_session_id,
  referral_entry_source = 'invite_link',
}: ReferralLoginMetadata): ReferralLoginMetadata => {
  const inviteCode = normalizeReferralInviteCode(invite_code);
  if (!inviteCode) {
    return {};
  }
  const sessionId =
    String(referral_session_id || '').trim() || createSessionId();
  const source = isReferralEntrySource(referral_entry_source)
    ? referral_entry_source
    : 'invite_link';
  const context: StoredReferralContext = {
    invite_code: inviteCode,
    referral_session_id: sessionId,
    referral_entry_source: source,
    updated_at: Date.now(),
  };
  if (isBrowser()) {
    window.localStorage.setItem(
      REFERRAL_CONTEXT_STORAGE_KEY,
      JSON.stringify(context),
    );
  }
  return {
    invite_code: context.invite_code,
    referral_session_id: context.referral_session_id,
    referral_entry_source: context.referral_entry_source,
  };
};

export const clearReferralContext = () => {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.removeItem(REFERRAL_CONTEXT_STORAGE_KEY);
};

export const buildReferralLoginPayload = (
  context: ReferralLoginMetadata = readReferralContext(),
) => {
  const inviteCode = normalizeReferralInviteCode(context.invite_code);
  if (!inviteCode) {
    return {};
  }
  return {
    invite_code: inviteCode,
    referral_session_id: String(context.referral_session_id || '').trim(),
    referral_entry_source: isReferralEntrySource(context.referral_entry_source)
      ? context.referral_entry_source
      : 'invite_link',
  };
};
