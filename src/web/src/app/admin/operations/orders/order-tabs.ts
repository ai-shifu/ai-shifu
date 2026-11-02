export type OperationOrdersTab = 'learn' | 'credits';

export function resolveOperationOrdersTab(
  tab?: string | null,
): OperationOrdersTab {
  return tab === 'credits' ? 'credits' : 'learn';
}
