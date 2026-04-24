import { cn } from '@/lib/utils';

export const ADMIN_TABLE_HEADER_CELL_CLASS =
  'relative border-r border-border last:border-r-0 sticky top-0 z-30 bg-muted';

export const ADMIN_TABLE_HEADER_CELL_CENTER_CLASS = cn(
  ADMIN_TABLE_HEADER_CELL_CLASS,
  'text-center',
);

export const ADMIN_TABLE_HEADER_LAST_CELL_CLASS =
  'relative sticky top-0 z-30 bg-muted';

export const ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS = cn(
  ADMIN_TABLE_HEADER_LAST_CELL_CLASS,
  'text-center',
);

export const ADMIN_TABLE_RESIZE_HANDLE_CLASS =
  'absolute top-0 right-0 h-full w-2 cursor-col-resize select-none';

const ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS =
  'shadow-[-4px_0_4px_rgba(0,0,0,0.02)] before:absolute before:inset-y-0 before:left-0 before:w-px before:bg-border before:content-[""]';

export const getAdminStickyRightHeaderClass = (className?: string) =>
  cn(
    'sticky right-0 top-0 z-40 bg-muted',
    ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS,
    className,
  );

export const getAdminStickyRightCellClass = (className?: string) =>
  cn(
    'sticky right-0 z-10 bg-white',
    ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS,
    className,
  );
