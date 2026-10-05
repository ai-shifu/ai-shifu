import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getRetakePolicy, setRetakePolicy } from '@/api/retake';
import { useTracking } from '@/hooks/useTracking';
import { useSingleFlight } from '@/hooks/useSingleFlight';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';

export function RetakeSettingsSection({ courseId }: { courseId: string }) {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const trackRef = useRef(trackEvent);
  trackRef.current = trackEvent;
  const [loadFailed, setLoadFailed] = useState(false);
  const [policy, setPolicy] = useState<{
    configured: boolean;
    limit: number | null;
  }>();
  const [available, setAvailable] = useState(false);
  const [value, setValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const identity = useRef(courseId);
  identity.current = courseId;
  useEffect(() => {
    let active = true;
    setAvailable(false);
    setLoadFailed(false);
    setPolicy(undefined);
    const trackLoad = (result: 'available' | 'unavailable' | 'failed') => {
      try {
        void Promise.resolve(
          trackRef.current('teacher_retake_policy_loaded', {
            shifu_bid: courseId,
            result,
          }),
        ).catch(() => {});
      } catch {}
    };
    setSaved(false);
    getRetakePolicy(courseId)
      .then(policy => {
        if (!active) return;
        setAvailable(policy.available);
        setPolicy(policy);
        trackLoad(policy.available ? 'available' : 'unavailable');
        setValue(policy.limit === null ? '' : String(policy.limit));
      })
      .catch(() => {
        if (!active) return;
        setLoadFailed(true);
        trackLoad('failed');
      });
    return () => {
      active = false;
    };
  }, [courseId]);
  const limit = value === '' ? null : Number(value);
  const valid =
    limit === null ||
    (/^\d+$/.test(value) && Number.isSafeInteger(limit) && limit <= 2147483647);
  const save = useSingleFlight(async () => {
    if (!valid || !available) return;
    setSaving(true);
    setSaved(false);
    let success = false;
    try {
      const updated = await setRetakePolicy(courseId, limit);
      success = true;
      if (identity.current === courseId) {
        setPolicy(updated);
        setSaved(true);
      }
    } catch {
      // The shared request layer displays the localized error.
    } finally {
      if (identity.current === courseId) setSaving(false);
      try {
        void Promise.resolve(
          trackEvent('teacher_retake_policy_result', {
            shifu_bid: courseId,
            result: success ? 'success' : 'failed',
            limit: limit ?? -1,
          }),
        ).catch(() => {});
      } catch {}
    }
  });
  if (loadFailed)
    return <p role='alert'>{t('module.lesson.retake.policyLoadFailed')}</p>;
  if (!available) return null;
  return (
    <section className='mb-6 space-y-2 border-t pt-4'>
      <label
        htmlFor='lesson-retake-limit'
        className='text-sm font-medium'
      >
        {t('module.lesson.retake.settingTitle')}
      </label>
      <p className='text-xs text-muted-foreground'>
        {t('module.lesson.retake.settingHelp')}
      </p>
      <p
        role='status'
        className='text-xs text-muted-foreground'
      >
        {!policy?.configured
          ? t('module.lesson.retake.notConfigured')
          : policy.limit === null
            ? t('module.lesson.retake.unlimited')
            : t('module.lesson.retake.currentLimit', { count: policy.limit })}
      </p>
      <Input
        id='lesson-retake-limit'
        inputMode='numeric'
        value={value}
        disabled={saving}
        placeholder={t('module.lesson.retake.unlimited')}
        onChange={event => {
          setValue(event.target.value);
          setSaved(false);
        }}
      />
      {!valid && (
        <p
          role='alert'
          className='text-sm text-destructive'
        >
          {t('module.lesson.retake.invalid')}
        </p>
      )}
      <Button
        type='button'
        variant='outline'
        disabled={saving || !valid}
        onClick={() => {
          void save();
        }}
      >
        {t('module.lesson.retake.save')}
      </Button>
      {saved && (
        <p
          role='status'
          className='text-xs text-muted-foreground'
        >
          {t('module.lesson.retake.saved')}
        </p>
      )}
    </section>
  );
}
