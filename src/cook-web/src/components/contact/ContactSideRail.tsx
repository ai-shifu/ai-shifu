import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

export const CONTACT_PAGE_URL = 'https://ai-shifu.cn/contact.html';
export const CONTACT_RAIL_I18N_KEY = 'component.navigation.contactUs';

interface ContactSideRailProps {
  className?: string;
  href?: string;
  label?: string;
}

export function ContactSideRail({
  className,
  href = CONTACT_PAGE_URL,
  label,
}: ContactSideRailProps) {
  const { t } = useTranslation();
  const resolvedLabel = label ?? t(CONTACT_RAIL_I18N_KEY);

  return (
    <div
      className={cn(
        'pointer-events-none fixed bottom-[100px] right-0 z-[300] hidden text-right md:block',
        className,
      )}
      data-testid='contact-side-rail'
    >
      <a
        href={href}
        target='_blank'
        rel='noopener noreferrer'
        aria-label={resolvedLabel}
        className='pointer-events-auto relative ml-auto mt-2 flex h-[100px] w-10 cursor-pointer items-center justify-center rounded bg-primary transition-colors duration-200 hover:bg-primary/95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'
      >
        <span className='inline-block w-4 select-none break-all text-base leading-[18px] text-primary-foreground'>
          {resolvedLabel}
        </span>
      </a>
    </div>
  );
}
