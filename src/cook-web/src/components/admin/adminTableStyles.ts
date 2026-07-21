import { cn } from '@/lib/utils';

export const ADMIN_TABLE_SHELL_CLASS =
  'rounded-xl border border-[var(--base-border,#E5E5E5)] bg-white shadow-none';

export const ADMIN_TABLE_HEADER_BASE_CLASS =
  '!h-[var(--height-h-10,40px)] !min-w-[85px] gap-[10px] !border-r-0 !border-b !border-[var(--base-border,#E5E5E5)] !bg-[var(--base-muted,#F5F5F5)] !px-[var(--spacing-2,8px)] !text-left !text-[length:var(--text-sm-font-size,14px)] not-italic !font-[var(--font-weight-medium,500)] !leading-[var(--text-sm-line-height,20px)] !text-[var(--base-foreground,#0A0A0A)]';

export const ADMIN_TABLE_BODY_CELL_BASE_CLASS =
  '!h-[53px] !min-w-[85px] !border-r-0 !p-[var(--spacing-2,8px)] !text-left !align-middle !text-[length:var(--text-sm-font-size,14px)] not-italic !font-[var(--font-weight-normal,400)] !leading-[var(--text-sm-line-height,20px)] !text-[var(--base-foreground,#0A0A0A)]';

export const ADMIN_TABLE_DESCENDANT_CLASS =
  '[&_thead]:!bg-[var(--base-muted,#F5F5F5)] [&_thead_tr]:!border-[var(--base-border,#E5E5E5)] [&_thead_th]:!h-[var(--height-h-10,40px)] [&_thead_th]:!min-w-[85px] [&_thead_th]:gap-[10px] [&_thead_th]:!border-r-0 [&_thead_th]:!border-b [&_thead_th]:!border-[var(--base-border,#E5E5E5)] [&_thead_th]:!bg-[var(--base-muted,#F5F5F5)] [&_thead_th]:!px-[var(--spacing-2,8px)] [&_thead_th]:!text-left [&_thead_th]:!text-[length:var(--text-sm-font-size,14px)] [&_thead_th]:not-italic [&_thead_th]:!font-[var(--font-weight-medium,500)] [&_thead_th]:!leading-[var(--text-sm-line-height,20px)] [&_thead_th]:!text-[var(--base-foreground,#0A0A0A)] [&_thead_th:first-child]:!pl-[var(--spacing-4,16px)] [&_tbody_tr:hover_td]:!bg-[var(--base-muted,#F5F5F5)] [&_tbody_td:not([colspan])]:!h-[53px] [&_tbody_td:not([colspan])]:!min-w-[85px] [&_tbody_td:not([colspan])]:!border-r-0 [&_tbody_td:not([colspan])]:!p-[var(--spacing-2,8px)] [&_tbody_td:not([colspan])]:!text-left [&_tbody_td:not([colspan])]:!align-middle [&_tbody_td:not([colspan])]:!text-[length:var(--text-sm-font-size,14px)] [&_tbody_td:not([colspan])]:not-italic [&_tbody_td:not([colspan])]:!font-[var(--font-weight-normal,400)] [&_tbody_td:not([colspan])]:!leading-[var(--text-sm-line-height,20px)] [&_tbody_td:not([colspan])]:!text-[var(--base-foreground,#0A0A0A)] [&_tbody_td:first-child:not([colspan])]:!pl-[var(--spacing-4,16px)] [&_tbody_td:not([colspan])_*]:!text-left';

export const ADMIN_TABLE_HEADER_CELL_CLASS = cn(
  'relative sticky top-0 z-30 !border-r-0 last:!border-r-0',
  ADMIN_TABLE_HEADER_BASE_CLASS,
);

export const ADMIN_TABLE_HEADER_CELL_CENTER_CLASS =
  ADMIN_TABLE_HEADER_CELL_CLASS;

export const ADMIN_TABLE_HEADER_LAST_CELL_CLASS = cn(
  'relative sticky top-0 z-30',
  ADMIN_TABLE_HEADER_BASE_CLASS,
);

export const ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS =
  ADMIN_TABLE_HEADER_LAST_CELL_CLASS;

export const ADMIN_TABLE_RESIZE_HANDLE_CLASS =
  'absolute top-0 right-0 h-full w-2 cursor-col-resize select-none';

const ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS = 'shadow-none before:content-none';

export const getAdminStickyRightHeaderClass = (className?: string) =>
  cn(
    'sticky right-0 top-0 z-40',
    ADMIN_TABLE_HEADER_BASE_CLASS,
    ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS,
    className,
  );

export const getAdminStickyRightCellClass = (className?: string) =>
  cn(
    'sticky right-0 z-10 bg-white',
    ADMIN_TABLE_BODY_CELL_BASE_CLASS,
    ADMIN_TABLE_STICKY_RIGHT_SHADOW_CLASS,
    className,
  );
