import { useEnvStore } from '@/c-store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { EnvStoreState } from '@/c-types/store';
import { cn } from '@/lib/utils';
import { Headset } from 'lucide-react';
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
        'pointer-events-none fixed bottom-[100px] right-0 z-[300] hidden md:block',
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
        title={resolvedLabel}
        className='pointer-events-auto group relative ml-auto flex h-10 w-10 cursor-pointer items-center justify-start overflow-hidden rounded-l-md bg-primary text-primary-foreground shadow-lg shadow-black/15 transition-[width] duration-200 hover:w-auto focus-visible:w-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'
      >
        <span
          className='flex h-10 w-10 shrink-0 items-center justify-center'
          data-testid='contact-side-rail-trigger'
        >
          <Headset
            className='h-6 w-6'
            aria-hidden='true'
          />
        </span>
        <span
          className='pointer-events-none max-w-0 whitespace-nowrap pr-0 text-sm font-medium leading-5 opacity-0 transition-[max-width,opacity,padding] duration-200 group-hover:max-w-56 group-hover:pr-4 group-hover:opacity-100 group-focus-visible:max-w-56 group-focus-visible:pr-4 group-focus-visible:opacity-100'
          data-testid='contact-side-rail-label'
        >
          {resolvedLabel}
        </span>
      </a>
    </div>
  );
}
