import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

interface PreviewHeaderBannerProps {
  className?: string;
}

export const PreviewHeaderBanner = ({
  className,
}: PreviewHeaderBannerProps) => {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        'w-full bg-primary/10 text-[var(--primary,#0F63EE)]',
        className,
      )}
    >
      <div className='flex min-h-10 w-full items-center px-4 py-2 text-[14px] font-medium leading-5 md:text-[15px]'>
        {t('module.preview.previewModeBanner')}
      </div>
    </div>
  );
};

export default memo(PreviewHeaderBanner);
