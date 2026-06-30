'use client';

import { ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { cn } from '@/lib/utils';

export type AdminRowActionItem = {
  key: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  hidden?: boolean;
};

type AdminRowActionsProps = {
  label: string;
  ariaLabel?: string;
  actions: AdminRowActionItem[];
  align?: 'start' | 'center' | 'end';
  className?: string;
};

const ADMIN_ROW_ACTION_TRIGGER_CLASS =
  'inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-sm font-normal text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2';

export default function AdminRowActions({
  label,
  ariaLabel,
  actions,
  align = 'center',
  className,
}: AdminRowActionsProps) {
  const visibleActions = actions.filter(action => !action.hidden);

  if (!visibleActions.length) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type='button'
          aria-label={ariaLabel}
          className={cn(ADMIN_ROW_ACTION_TRIGGER_CLASS, className)}
        >
          {label}
          <ChevronDown className='h-3.5 w-3.5' />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align}>
        {visibleActions.map(action => (
          <DropdownMenuItem
            key={action.key}
            disabled={action.disabled}
            onClick={() => {
              if (!action.disabled) {
                action.onClick();
              }
            }}
          >
            {action.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
