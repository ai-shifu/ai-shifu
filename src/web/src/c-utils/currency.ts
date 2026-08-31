export const getCurrencyCode = (symbol?: string) => {
  if (!symbol) {
    return 'CNY';
  }
  const normalized = symbol.trim().toUpperCase();
  if (symbol.includes('$') || normalized === 'USD') {
    return 'USD';
  }
  if (symbol.includes('¥') || symbol.includes('￥') || normalized === 'CNY') {
    return 'CNY';
  }
  return normalized || 'CNY';
};
