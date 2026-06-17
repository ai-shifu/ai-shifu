export const PROFILE_ONBOARDING_ALLOWED_VARIABLE_KEYS = [
  'sys_user_nickname',
  'sys_user_style',
  'sys_user_background',
] as const;

export type ProfileOnboardingVariableKey =
  (typeof PROFILE_ONBOARDING_ALLOWED_VARIABLE_KEYS)[number];

export type ProfileOnboardingStep = {
  id: string;
  intro: string;
  options: Array<{ label: string; value: string }>;
  prompt: string;
  type: 'text' | 'choice';
  variableKey: string;
};

const INTERACTION_PATTERN = /\?\[([\s\S]*?)\]/g;
const VARIABLE_MARKER_PATTERN = /%\{\{\s*([^}\s]+)\s*\}\}/g;
const STEP_VARIABLE_PATTERN = /%\{\{\s*([^}\s]+)\s*\}\}\s*([\s\S]*)$/;

const normalizeFlowText = (value: string) =>
  value
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .join('\n');

const parseStepBody = (
  body: string,
  index: number,
  intro: string,
): ProfileOnboardingStep | null => {
  const match = body.match(STEP_VARIABLE_PATTERN);
  if (!match?.[1]) {
    return null;
  }

  const variableKey = match[1].trim();
  const rest = (match[2] || '').trim();
  const isTextInput = rest.startsWith('...');
  const textPrompt = isTextInput ? rest.slice(3).trim() : rest;
  const optionLabels =
    !isTextInput && rest.includes('|')
      ? rest
          .split('|')
          .map(option => option.trim())
          .filter(Boolean)
      : [];

  return {
    id: `${variableKey}-${index}`,
    intro,
    options: optionLabels.map(option => ({ label: option, value: option })),
    prompt: optionLabels.length > 1 ? '' : textPrompt,
    type: optionLabels.length > 1 ? 'choice' : 'text',
    variableKey,
  };
};

export const parseProfileOnboardingFlow = (
  markdownflow?: string | null,
): ProfileOnboardingStep[] => {
  const source = String(markdownflow || '');
  const steps: ProfileOnboardingStep[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;

  INTERACTION_PATTERN.lastIndex = 0;
  while ((match = INTERACTION_PATTERN.exec(source)) !== null) {
    const intro = normalizeFlowText(source.slice(cursor, match.index));
    const step = parseStepBody(match[1] || '', steps.length, intro);
    if (step) {
      steps.push(step);
    }
    cursor = match.index + match[0].length;
    if (INTERACTION_PATTERN.lastIndex === match.index) {
      INTERACTION_PATTERN.lastIndex += 1;
    }
  }
  INTERACTION_PATTERN.lastIndex = 0;

  return steps;
};

export const collectProfileOnboardingVariableKeys = (
  markdownflow?: string | null,
): string[] => {
  const source = String(markdownflow || '');
  const collected = new Set<string>();
  let match: RegExpExecArray | null;

  VARIABLE_MARKER_PATTERN.lastIndex = 0;
  while ((match = VARIABLE_MARKER_PATTERN.exec(source)) !== null) {
    if (match[1]) {
      collected.add(match[1].trim());
    }
    if (VARIABLE_MARKER_PATTERN.lastIndex === match.index) {
      VARIABLE_MARKER_PATTERN.lastIndex += 1;
    }
  }
  VARIABLE_MARKER_PATTERN.lastIndex = 0;

  return Array.from(collected);
};

export const getInvalidProfileOnboardingVariableKeys = (
  markdownflow: string,
  allowedKeys: string[],
) => {
  const allowed = new Set(allowedKeys);
  return collectProfileOnboardingVariableKeys(markdownflow).filter(
    key => !allowed.has(key),
  );
};
