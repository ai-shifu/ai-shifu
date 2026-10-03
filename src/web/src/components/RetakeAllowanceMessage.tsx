import { useTranslation } from 'react-i18next';
import type { RetakeStatus } from '@/api/retake';

export function RetakeAllowanceMessage({
  status,
  loading,
  failed,
}: {
  status?: RetakeStatus;
  loading: boolean;
  failed?: boolean;
}) {
  const { t } = useTranslation();
  let message = '';
  if (loading) message = t('module.lesson.retake.loading');
  else if (failed) message = t('module.lesson.retake.loadFailed');
  else if (status?.available) {
    if (status.in_progress) message = t('module.lesson.retake.busy');
    else if (!status.allowed) message = t('module.lesson.retake.exhausted');
    else if (status.remaining === 1) message = t('module.lesson.retake.last');
    else if (status.remaining !== null)
      message = t('module.lesson.retake.remaining', {
        count: status.remaining,
      });
  }
  return message ? (
    <p
      role='status'
      className='text-sm text-muted-foreground'
    >
      {message}
    </p>
  ) : null;
}
