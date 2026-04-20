import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';

type AdminBillingPagerProps = {
  canGoNext: boolean;
  canGoPrev: boolean;
  onNext: () => void;
  onPrev: () => void;
  page: number;
  pageCount: number;
  total: number;
};

export function AdminBillingPager({
  canGoNext,
  canGoPrev,
  onNext,
  onPrev,
  page,
  pageCount,
  total,
}: AdminBillingPagerProps) {
  const { t } = useTranslation();

  return (
    <div className='flex flex-wrap items-center justify-between gap-3'>
      <div className='text-sm text-slate-500'>
        {t('module.billing.admin.pagination.page', {
          page,
          pageCount,
          total,
        })}
      </div>
      <div className='flex gap-2'>
        <Button
          variant='outline'
          disabled={!canGoPrev}
          onClick={onPrev}
        >
          {t('common.page.previous')}
        </Button>
        <Button
          variant='outline'
          disabled={!canGoNext}
          onClick={onNext}
        >
          {t('common.page.next')}
        </Button>
      </div>
    </div>
  );
}
