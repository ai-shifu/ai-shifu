import { v4 as uuid } from 'uuid';

const pending = new Map<string, string>();
export function retakeRequestIdentity(scope: string): string {
  const key = `lesson-retake-request:${scope}`;
  let value = pending.get(key);
  try {
    value ||= sessionStorage.getItem(key) || undefined;
  } catch {}
  value ||= uuid();
  pending.set(key, value);
  try {
    sessionStorage.setItem(key, value);
  } catch {}
  return value;
}
export function finishRetakeRequest(scope: string) {
  const key = `lesson-retake-request:${scope}`;
  pending.delete(key);
  try {
    sessionStorage.removeItem(key);
  } catch {}
}
