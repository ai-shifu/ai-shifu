import { useEnvStore } from '@/c-store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { EnvStoreState } from '@/c-types/store';
import { cn } from '@/lib/utils';
import { usePathname } from 'next/navigation';
import { useTranslation } from 'react-i18next';

export const CONTACT_RAIL_I18N_KEY = 'component.navigation.contactUs';
export const CONTACT_RAIL_CLICK_EVENT = 'contact_us_click';

interface ContactSideRailProps {
  className?: string;
  label?: string;
}

export function ContactSideRail({ className, label }: ContactSideRailProps) {
  const { t } = useTranslation();
  const pathname = usePathname();
  const { trackEvent } = useTracking();
  const contactUsUrl = useEnvStore(
    (state: EnvStoreState) => state.contactUsUrl,
  );
  const resolvedLabel = label ?? t(CONTACT_RAIL_I18N_KEY);
  const resolvedHref = contactUsUrl.trim();

  if (!resolvedHref) {
    return null;
  }

  return (
    <div
      className={cn(
        'pointer-events-none fixed bottom-[100px] right-0 z-[300] hidden text-right md:block',
        className,
      )}
      data-testid='contact-side-rail'
    >
      <a
        href={resolvedHref}
        target='_blank'
        rel='noopener noreferrer'
        aria-label={resolvedLabel}
        onClick={() => {
          trackEvent(CONTACT_RAIL_CLICK_EVENT, {
            page_path: pathname || '',
            target_url: resolvedHref,
          });
        }}
        className='pointer-events-auto relative ml-auto mt-2 flex h-[100px] w-10 cursor-pointer items-center justify-center rounded bg-primary transition-colors duration-200 hover:bg-primary/95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'
      >
        <span className='inline-block w-4 select-none break-all text-base leading-[18px] text-primary-foreground'>
          {resolvedLabel}
        </span>
      </a>
    </div>
  );
}
