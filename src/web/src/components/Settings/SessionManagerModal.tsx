import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Monitor, Smartphone, Terminal } from 'lucide-react';

import SettingBaseModal from './SettingBaseModal';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/hooks/useToast';
import apiService from '@/api';
import { cn } from '@/lib/utils';
import { EVENT_NAMES, useTracking } from '@/hooks/useTracking';

export type LoginSession = {
  session_bid: string;
  source: string;
  device_name: string;
  device_os: string;
  created_ip: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  is_current: boolean;
};

const formatMoment = (value: string, locale: string): string => {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleString(locale);
};

export const SessionManagerModal = ({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) => {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { trackEvent } = useTracking();

  const [sessions, setSessions] = useState<LoginSession[]>([]);
  // Only the first load shows a spinner: reloading after a revoke must not
  // blank out the list the user is looking at.
  const [loaded, setLoaded] = useState(false);
  const [busyBid, setBusyBid] = useState('');

  // `t`, `toast` and `trackEvent` are rebuilt by their hooks on every render.
  // A data callback that depends on them is a new function each time, and an
  // effect depending on that callback re-runs without end.
  // Translate during render, where the key is a visible literal the
  // translation-usage check can find, and keep only the resulting strings in a
  // ref so the callbacks below stay free of unstable dependencies.
  const fallbackText = {
    load: t('module.settings.sessionsLoadFailed'),
    revoke: t('module.settings.sessionsRevokeFailed'),
  };

  const textRef = useRef(fallbackText);
  const toastRef = useRef(toast);
  const trackRef = useRef(trackEvent);
  useEffect(() => {
    textRef.current = fallbackText;
    toastRef.current = toast;
    trackRef.current = trackEvent;
  });

  const reportFailure = useCallback(
    (error: unknown, fallback: 'load' | 'revoke') => {
      toastRef.current({
        title: (error as Error)?.message || textRef.current[fallback],
        variant: 'destructive',
      });
    },
    [],
  );

  // Marks the newest request so a slower earlier one cannot land after it, and
  // so a response arriving after the dialog closed is dropped instead of being
  // rendered over whatever is shown next.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    try {
      const data = await apiService.listSessions({});
      if (requestId !== requestIdRef.current) {
        return;
      }
      setSessions(Array.isArray(data) ? (data as LoginSession[]) : []);
    } catch (error) {
      if (requestId !== requestIdRef.current) {
        return;
      }
      reportFailure(error, 'load');
    } finally {
      if (requestId === requestIdRef.current) {
        setLoaded(true);
      }
    }
  }, [reportFailure]);

  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    if (!open) {
      // Invalidate anything in flight and drop what was on screen, so
      // reopening never shows a previous account's sessions.
      requestIdRef.current += 1;
      setLoaded(false);
      setSessions([]);
      return;
    }
    void loadRef.current();
  }, [open]);

  const revokeOne = useCallback(
    async (session: LoginSession) => {
      setBusyBid(session.session_bid);
      try {
        await apiService.revokeSession({ session_bid: session.session_bid });
        void trackRef.current(EVENT_NAMES.SESSION_REVOKED, {
          source: session.source,
        });
        await loadRef.current();
      } catch (error) {
        reportFailure(error, 'revoke');
      } finally {
        setBusyBid('');
      }
    },
    [reportFailure],
  );

  const revokeOthers = useCallback(async () => {
    setBusyBid('all');
    try {
      await apiService.revokeOtherSessions({});
      void trackRef.current(EVENT_NAMES.SESSION_REVOKED_OTHERS, {});
      await loadRef.current();
    } catch (error) {
      reportFailure(error, 'revoke');
    } finally {
      setBusyBid('');
    }
  }, [reportFailure]);

  const iconFor = (session: LoginSession) => {
    if (session.source === 'cli') {
      return <Terminal size={16} />;
    }
    if (/iOS|iPadOS|Android/i.test(session.device_os)) {
      return <Smartphone size={16} />;
    }
    return <Monitor size={16} />;
  };

  const describeDevice = (session: LoginSession): string => {
    const parts = [session.device_name, session.device_os].filter(Boolean);
    return parts.length > 0
      ? parts.join(' · ')
      : t('module.settings.sessionsUnknownDevice');
  };

  const others = sessions.filter(session => !session.is_current);

  return (
    <SettingBaseModal
      open={open}
      onClose={onClose}
      onOk={onClose}
      okText={t('common.core.close')}
      title={t('module.settings.sessions')}
    >
      <div className='space-y-3'>
        <p className='text-sm text-muted-foreground'>
          {t('module.settings.sessionsDescription')}
        </p>

        {!loaded ? (
          <div className='flex justify-center py-6'>
            <Loader2 className='h-6 w-6 animate-spin text-primary' />
          </div>
        ) : (
          <ul className='space-y-2'>
            {sessions.map(session => (
              <li
                key={session.session_bid}
                className={cn(
                  'flex items-start justify-between gap-3 rounded-md border p-3',
                  session.is_current && 'border-primary',
                )}
              >
                <div className='min-w-0 space-y-1'>
                  <div className='flex items-center gap-2 text-sm font-medium'>
                    {iconFor(session)}
                    <span className='truncate'>{describeDevice(session)}</span>
                    {session.is_current ? (
                      <span className='shrink-0 text-xs text-primary'>
                        {t('module.settings.sessionsCurrent')}
                      </span>
                    ) : null}
                  </div>
                  <div className='text-xs text-muted-foreground'>
                    {[
                      session.source === 'cli'
                        ? t('module.settings.sessionsSourceCli')
                        : t('module.settings.sessionsSourceWeb'),
                      session.created_ip,
                      formatMoment(session.last_seen_at, i18n.language),
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </div>
                {session.is_current ? null : (
                  <Button
                    variant='outline'
                    size='sm'
                    disabled={Boolean(busyBid)}
                    onClick={() => void revokeOne(session)}
                  >
                    {t('module.settings.sessionsRevoke')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}

        {loaded && others.length > 0 ? (
          <Button
            variant='outline'
            className='w-full'
            disabled={Boolean(busyBid)}
            onClick={() => void revokeOthers()}
          >
            {t('module.settings.sessionsRevokeOthers')}
          </Button>
        ) : null}
      </div>
    </SettingBaseModal>
  );
};

export default SessionManagerModal;
