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
    <div className={cn('w-full bg-sky-100 text-sky-800', className)}>
      <div className='flex min-h-10 w-full items-center justify-center px-4 py-2 text-center text-[14px] font-medium leading-5 md:text-[15px]'>
        {t('module.preview.previewModeBanner')}
      </div>
    </div>
  );
};

export default memo(PreviewHeaderBanner);
