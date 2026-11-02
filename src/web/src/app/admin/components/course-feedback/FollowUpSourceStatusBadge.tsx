'use client';

import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

type FollowUpSourceStatusBadgeProps = {
  hasSourceOutput: boolean;
  resolvedLabel: string;
  missingLabel: string;
};

/**
 * Shows whether the lesson output a follow-up was asked about could be
 * located.
 */
export default function FollowUpSourceStatusBadge({
  hasSourceOutput,
  resolvedLabel,
  missingLabel,
}: FollowUpSourceStatusBadgeProps) {
  return (
    <Badge
      variant='outline'
      className={cn(
        'border px-2 py-0.5 text-[11px] font-medium',
        hasSourceOutput
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-amber-200 bg-amber-50 text-amber-700',
      )}
    >
      {hasSourceOutput ? resolvedLabel : missingLabel}
    </Badge>
  );
}
