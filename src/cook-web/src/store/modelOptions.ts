import type { ModelOption } from '@/types/shifu';

export const normalizeModelOptions = (list: any): ModelOption[] => {
  if (!Array.isArray(list)) return [];
  const seen = new Set<string>();
  const options: ModelOption[] = [];

  list.forEach(item => {
    if (typeof item === 'string') {
      const value = item.trim();
      if (value && !seen.has(value)) {
        seen.add(value);
        options.push({ value, label: value });
      }
      return;
    }

    if (item && typeof item === 'object') {
      const value = String(item.model || item.value || '').trim();
      if (!value || seen.has(value)) {
        return;
      }
      const labelSource =
        item.display_name || item.displayName || item.label || value;
      const label = String(labelSource || value).trim() || value;
      const rawMultiplier = item.credit_multiplier ?? item.creditMultiplier;
      const parsedMultiplier = Number(rawMultiplier);
      const creditMultiplier =
        Number.isFinite(parsedMultiplier) && parsedMultiplier > 0
          ? Math.ceil(parsedMultiplier)
          : null;
      seen.add(value);
      options.push({ value, label, creditMultiplier });
    }
  });

  return options;
};
