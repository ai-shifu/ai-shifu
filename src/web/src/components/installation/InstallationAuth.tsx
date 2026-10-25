'use client';

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import {
  getInstallationStatus,
  initializeAdministrator,
  loginLocalAdministrator,
  type InstallationStatus,
} from '@/api/installation';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { useTracking } from '@/hooks/useTracking';
import { useUserStore } from '@/store/useUserStore';
import {
  buildInstallationExposure,
  buildInstallationResult,
  INSTALLATION_AUTH_ATTEMPT,
  INSTALLATION_AUTH_EXPOSURE,
  INSTALLATION_AUTH_RESULT,
  type InstallationFailureCategory,
  type InstallationSurface,
} from './installationAnalytics';
import {
  getLocalAdminRedirect,
  isSecureInstallationOrigin,
} from './installationRouting';

const installationErrorKeys = {
  12001: 'server.installation.setupUnavailable',
  12002: 'server.installation.invalidSetupToken',
  12003: 'server.installation.setupComplete',
  12004: 'server.installation.invalidUsername',
  12005: 'server.installation.usernameUnavailable',
  12006: 'server.installation.localLoginUnavailable',
  12007: 'server.installation.invalidSetupOrigin',
  12008: 'server.installation.passwordTooLong',
  12009: 'server.installation.setupRateLimited',
} as const;

const getErrorCode = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object') return undefined;
  const code = (error as { code?: unknown }).code;
  return typeof code === 'number' ? code : undefined;
};

export const InstallationAuth = ({
  surface,
}: {
  surface: Exclude<InstallationSurface, 'local_password_change'>;
}) => {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const login = useUserStore(state => state.login);
  const { trackEvent } = useTracking();
  const [status, setStatus] = useState<InstallationStatus | null>(null);
  const [statusFailed, setStatusFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [setupToken, setSetupToken] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [offerLocalLogin, setOfferLocalLogin] = useState(false);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const seenSurfaces = useRef(new Set<InstallationSurface>());
  const setup = surface === 'setup';
  const secure =
    typeof window !== 'undefined' &&
    isSecureInstallationOrigin(window.location);
  const available = Boolean(
    status &&
    (setup
      ? status.setup_required
      : !status.setup_required && status.local_admin_login_enabled),
  );

  const emit = useCallback(
    (name: string, data: Record<string, string>) => {
      try {
        void Promise.resolve(trackEvent(name, data)).catch(() => {});
      } catch {}
    },
    [trackEvent],
  );

  useEffect(() => {
    let active = true;
    setStatus(null);
    setStatusFailed(false);
    getInstallationStatus()
      .then(value => {
        if (active) setStatus(value);
      })
      .catch(() => {
        if (active) setStatusFailed(true);
      });
    return () => {
      active = false;
    };
  }, [reload]);

  useEffect(() => {
    setSetupToken('');
    setPassword('');
    setConfirmation('');
    setErrorMessage('');
    setOfferLocalLogin(false);
  }, [surface]);

  useEffect(() => {
    if (!available || !secure || seenSurfaces.current.has(surface)) return;
    seenSurfaces.current.add(surface);
    emit(INSTALLATION_AUTH_EXPOSURE, buildInstallationExposure(surface));
  }, [available, emit, secure, surface]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting.current || !available || !secure) return;
    setErrorMessage('');
    const normalizedUsername = username.trim().toLowerCase();
    if (!normalizedUsername || !password || (setup && !setupToken.trim())) {
      setErrorMessage(t('module.installation.validationRequired'));
      return;
    }
    if (!/^[a-z][a-z0-9_.-]{2,63}$/.test(normalizedUsername)) {
      setErrorMessage(t('module.installation.usernameInvalid'));
      return;
    }
    if (new Blob([password]).size > 72) {
      setErrorMessage(t('server.installation.passwordTooLong'));
      return;
    }
    if (
      setup &&
      (Array.from(password).length < 8 ||
        !/[a-zA-Z]/.test(password) ||
        !/[0-9]/.test(password))
    ) {
      setErrorMessage(t('module.installation.passwordInvalid'));
      return;
    }
    if (setup && password !== confirmation) {
      setErrorMessage(t('module.installation.passwordMismatch'));
      return;
    }
    const returnPath = getLocalAdminRedirect(window.location.search);
    submitting.current = true;
    setBusy(true);
    setOfferLocalLogin(false);
    const payload = {
      username: normalizedUsername,
      password,
      language: i18n.resolvedLanguage || i18n.language || 'en-US',
    };
    const token = setupToken.trim();
    setPassword('');
    setConfirmation('');
    setSetupToken('');
    emit(INSTALLATION_AUTH_ATTEMPT, buildInstallationExposure(surface));
    let sessionStage = false;
    let authenticated = false;
    try {
      const session = await (setup
        ? initializeAdministrator({ ...payload, setup_token: token })
        : loginLocalAdministrator(payload));
      sessionStage = true;
      if (!session?.userInfo || !session.token) {
        throw new Error('Invalid administrator session response');
      }
      await login(session.userInfo, session.token);
      authenticated = true;
      emit(
        INSTALLATION_AUTH_RESULT,
        buildInstallationResult(surface, 'success', 'none'),
      );
    } catch (error) {
      const code = getErrorCode(error);
      const category: InstallationFailureCategory = sessionStage
        ? 'session_unavailable'
        : code && code !== 12001
          ? 'credentials_rejected'
          : 'transport_or_service';
      const key =
        installationErrorKeys[code as keyof typeof installationErrorKeys];
      const uncertainSetup =
        setup && (sessionStage || !code || code === 12001 || code === 12003);
      setOfferLocalLogin(setup);
      setErrorMessage(
        uncertainSetup
          ? t('module.installation.sessionFailed')
          : key
            ? t(key)
            : t('module.installation.requestFailed'),
      );
      emit(
        INSTALLATION_AUTH_RESULT,
        buildInstallationResult(surface, 'failed', category),
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
    if (authenticated) {
      router.replace(returnPath);
    }
  };

  return (
    <main className='flex min-h-dvh items-center justify-center bg-stone-50 p-4'>
      <Card className='w-full max-w-md'>
        <CardHeader>
          <CardTitle>
            {t(
              setup
                ? 'module.installation.setupTitle'
                : 'module.installation.localLoginTitle',
            )}
          </CardTitle>
          <CardDescription>
            {t(
              setup
                ? 'module.installation.setupDescription'
                : 'module.installation.localLoginDescription',
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className='space-y-4'>
          {statusFailed ? (
            <div
              role='alert'
              className='space-y-3'
            >
              <p>{t('module.installation.statusFailed')}</p>
              <Button
                type='button'
                onClick={() => setReload(value => value + 1)}
              >
                {t('module.installation.retry')}
              </Button>
            </div>
          ) : !status ? (
            <p role='status'>{t('module.installation.checking')}</p>
          ) : !available ? (
            <p role='status'>
              {t(
                setup
                  ? 'module.installation.setupClosed'
                  : 'module.installation.localUnavailable',
              )}
            </p>
          ) : !secure ? (
            <p role='alert'>
              {t('module.installation.secureTransportRequired')}
            </p>
          ) : (
            <form
              onSubmit={event => void submit(event)}
              className='space-y-4'
            >
              {setup ? (
                <div className='space-y-2'>
                  <Label htmlFor='installation-code'>
                    {t('module.installation.codeLabel')}
                  </Label>
                  <Input
                    id='installation-code'
                    name='setup_token'
                    type='password'
                    autoComplete='off'
                    value={setupToken}
                    onChange={event => setSetupToken(event.target.value)}
                    disabled={busy}
                    maxLength={256}
                    aria-describedby='installation-code-help'
                  />
                  <p
                    id='installation-code-help'
                    className='text-sm text-muted-foreground'
                  >
                    {t('module.installation.codeHelp')}
                  </p>
                </div>
              ) : null}
              <div className='space-y-2'>
                <Label htmlFor='installation-username'>
                  {t('module.installation.usernameLabel')}
                </Label>
                <Input
                  id='installation-username'
                  name='username'
                  autoComplete='username'
                  autoCapitalize='none'
                  spellCheck={false}
                  value={username}
                  onChange={event => setUsername(event.target.value)}
                  disabled={busy}
                  maxLength={64}
                  aria-describedby={
                    setup ? 'installation-username-help' : undefined
                  }
                />
                {setup ? (
                  <p
                    id='installation-username-help'
                    className='text-sm text-muted-foreground'
                  >
                    {t('module.installation.usernameHelp')}
                  </p>
                ) : null}
              </div>
              <div className='space-y-2'>
                <Label htmlFor='installation-password'>
                  {t('module.installation.passwordLabel')}
                </Label>
                <Input
                  id='installation-password'
                  name='password'
                  type='password'
                  autoComplete={setup ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={event => setPassword(event.target.value)}
                  disabled={busy}
                  aria-describedby={
                    setup ? 'installation-password-help' : undefined
                  }
                />
                {setup ? (
                  <p
                    id='installation-password-help'
                    className='text-sm text-muted-foreground'
                  >
                    {t('module.installation.passwordHelp')}
                  </p>
                ) : null}
              </div>
              {setup ? (
                <div className='space-y-2'>
                  <Label htmlFor='installation-confirmation'>
                    {t('module.installation.confirmPasswordLabel')}
                  </Label>
                  <Input
                    id='installation-confirmation'
                    name='password_confirmation'
                    type='password'
                    autoComplete='new-password'
                    value={confirmation}
                    onChange={event => setConfirmation(event.target.value)}
                    disabled={busy}
                  />
                </div>
              ) : null}
              {errorMessage ? <p role='alert'>{errorMessage}</p> : null}
              {offerLocalLogin ? (
                <Link
                  href='/admin-login'
                  className='block text-primary underline'
                >
                  {t('module.installation.loginAfterSetup')}
                </Link>
              ) : null}
              <Button
                type='submit'
                disabled={busy}
                className='w-full'
              >
                {t(
                  setup
                    ? busy
                      ? 'module.installation.creating'
                      : 'module.installation.createAdmin'
                    : busy
                      ? 'module.installation.loggingIn'
                      : 'module.installation.login',
                )}
              </Button>
            </form>
          )}
          {status?.setup_required && !setup ? (
            <Link
              href='/setup'
              className='block text-primary underline'
            >
              {t('module.installation.setupLink')}
            </Link>
          ) : null}
          {setup &&
          status &&
          !status.setup_required &&
          status.local_admin_login_enabled ? (
            <Link
              href='/admin-login'
              className='block text-primary underline'
            >
              {t('module.installation.loginAfterSetup')}
            </Link>
          ) : null}
          {status && !status.setup_required ? (
            <Link
              href='/login?redirect=%2Fadmin'
              className='block text-sm text-primary underline'
            >
              {t('module.installation.otherLogin')}
            </Link>
          ) : null}
          {!setup ? (
            <p className='text-sm text-muted-foreground'>
              {t('module.installation.consoleRecovery')}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </main>
  );
};
