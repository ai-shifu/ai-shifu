export const LEARNING_MODE_OPTIONS = [
  {
    mode: 'listen',
    label: '听课',
  },
  {
    mode: 'read',
    label: '阅读',
  },
] as const;

export const LEARNING_MODE_LABELS = LEARNING_MODE_OPTIONS.reduce(
  (labels, option) => {
    labels[option.mode] = option.label;
    return labels;
  },
  {} as Record<(typeof LEARNING_MODE_OPTIONS)[number]['mode'], string>,
);
