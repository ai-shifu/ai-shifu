import { useTranslation } from 'react-i18next';
import type { RetakeStatus } from '@/api/retake';

export function RetakeAllowanceMessage({
  status,
  failed,
}: {
  status?: RetakeStatus;
  loading: boolean;
  failed?: boolean;
}) {
  const { t } = useTranslation();
  let message = '';
  if (failed) message = t('module.lesson.retake.loadFailed');
  else if (status?.available) {
    if (status.in_progress) message = t('module.lesson.retake.busy');
    else if (!status.allowed) message = t('module.lesson.retake.exhausted');
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
