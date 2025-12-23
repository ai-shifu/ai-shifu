'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/Tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { PhoneLogin } from '@/components/auth/PhoneLogin';
import { EmailLogin } from '@/components/auth/EmailLogin';
import { FeedbackForm } from '@/components/auth/FeedbackForm';
import Image, { type StaticImageData } from 'next/image';
import logoHorizontal from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import LanguageSelect from '@/components/language-select';
import { useTranslation } from 'react-i18next';
import i18n, { browserLanguage, normalizeLanguage } from '@/i18n';
import { environment } from '@/config/environment';
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';
import { TermsCheckbox } from '@/components/TermsCheckbox';
import { TermsConfirmDialog } from '@/components/auth/TermsConfirmDialog';
import { useToast } from '@/hooks/useToast';
import { useGoogleAuth } from '@/hooks/useGoogleAuth';
import { useUserStore } from '@/store';
import { useEnvStore } from '@/c-store';
import { EnvStoreState } from '@/c-types/store';

type LoginMethod = 'phone' | 'email' | 'google';

export default function AuthPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<'login' | 'feedback'>('login');
  const [isI18nReady, setIsI18nReady] = useState(false);
  const userInfo = useUserStore(state => state.userInfo);
  const [logoSrc, setLogoSrc] = useState<string | StaticImageData>(
    environment.logoWideUrl || logoHorizontal,
  );

  const logoWideUrl = useEnvStore((state: EnvStoreState) => state.logoWideUrl);
  const runtimeLoginMethods = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const runtimeDefaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );

  useEffect(() => {
    setLogoSrc(logoWideUrl || environment.logoWideUrl || logoHorizontal);
  }, [logoWideUrl]);

  const normalizedMethods = useMemo(() => {
    const fallback = environment.loginMethodsEnabled;
    const runtimeValue = runtimeLoginMethods as string | string[] | undefined;

    if (Array.isArray(runtimeValue) && runtimeValue.length > 0) {
      return runtimeValue;
    }
    if (typeof runtimeValue === 'string') {
      const parsed = runtimeValue
        .split(',')
        .map(method => method.trim())
        .filter(Boolean);
      if (parsed.length > 0) {
        return parsed;
      }
    }
    return fallback;
  }, [runtimeLoginMethods]);

  const defaultMethod =
    typeof runtimeDefaultLoginMethod === 'string' &&
    runtimeDefaultLoginMethod.trim() !== ''
      ? runtimeDefaultLoginMethod
      : environment.defaultLoginMethod;

  const isPhoneEnabled = normalizedMethods.includes('phone');
  const isEmailEnabled = normalizedMethods.includes('email');
  const isGoogleEnabled = normalizedMethods.includes('google');

  const availableMethods = useMemo<LoginMethod[]>(() => {
    const methods: LoginMethod[] = [];
    if (isPhoneEnabled) methods.push('phone');
    if (isEmailEnabled) methods.push('email');
    if (isGoogleEnabled) methods.push('google');
    return methods;
  }, [isEmailEnabled, isGoogleEnabled, isPhoneEnabled]);

  const initialLoginMethod = useMemo<LoginMethod>(() => {
    const normalizedDefault = defaultMethod as LoginMethod;
    if (normalizedDefault && availableMethods.includes(normalizedDefault)) {
      return normalizedDefault;
    }
    return availableMethods[0] ?? 'phone';
  }, [availableMethods, defaultMethod]);

  const [loginMethod, setLoginMethod] =
    useState<LoginMethod>(initialLoginMethod);
  const [language, setLanguage] = useState<string | null>(null);
  const manualLanguageRef = useRef(false);

  useEffect(() => {
    setLoginMethod(initialLoginMethod);
  }, [initialLoginMethod]);

  const searchParams = useSearchParams();
  const { toast } = useToast();
  const isInitialized = useUserStore(state => state.isInitialized);
  const isLoggedIn = useUserStore(state => state.isLoggedIn);

  const resolveRedirectPath = useCallback(() => {
    let redirect = searchParams.get('redirect');
    if (!redirect || redirect.charAt(0) !== '/') {
      redirect = '/admin';
    }
    return redirect;
  }, [searchParams]);

  const loginContext = useMemo(() => {
    const redirectPath = resolveRedirectPath();
    return redirectPath.startsWith('/admin') ? 'admin' : 'default';
  }, [resolveRedirectPath]);

  const handleAuthSuccess = () => {
    router.replace(resolveRedirectPath());
  };

  const handleFeedback = () => {
    setAuthMode('feedback');
  };

  const handleBackToLogin = () => {
    setAuthMode('login');
  };

  const { t, ready } = useTranslation();

  useEffect(() => {
    if (!isInitialized) {
      return;
    }

    const preferred = userInfo?.language
      ? normalizeLanguage(userInfo.language)
      : null;
    const nextLanguage = normalizeLanguage(preferred ?? browserLanguage);

    if (!nextLanguage) {
      return;
    }

    if (language === nextLanguage) {
      manualLanguageRef.current = false;
      return;
    }

    if (manualLanguageRef.current) {
      return;
    }

    let isCancelled = false;

    setIsI18nReady(false);

    const applyLanguage = async () => {
      try {
        await i18n.changeLanguage(nextLanguage);
        if (!isCancelled) {
          setLanguage(nextLanguage);
        }
      } catch (error) {
        console.error('Failed to change language', error);
      }
    };

    applyLanguage();

    return () => {
      isCancelled = true;
    };
  }, [browserLanguage, isInitialized, language, userInfo]);

  const handleManualLanguageChange = useCallback(
    async (value: string) => {
      const normalized = normalizeLanguage(value);
      if (!normalized || normalized === language) {
        return;
      }

      manualLanguageRef.current = true;
      setIsI18nReady(false);

      try {
        await i18n.changeLanguage(normalized);
        setLanguage(normalized);
      } catch (error) {
        console.error('Failed to change language', error);
      }
    },
    [language],
  );

  // Monitor i18n ready state to prevent language flash
  useEffect(() => {
    if (!language) {
      return;
    }

    const resolvedLanguage = i18n.resolvedLanguage ?? i18n.language;
    const defaultNamespaceOption = i18n.options.defaultNS;
    const defaultNamespace = Array.isArray(defaultNamespaceOption)
      ? defaultNamespaceOption[0]
      : (defaultNamespaceOption ?? 'common');
    const hasBundle = i18n.hasResourceBundle(language, defaultNamespace);

    if (!ready || resolvedLanguage !== language) {
      return;
    }

    if (hasBundle) {
      setIsI18nReady(true);
    }
  }, [language, ready]);

  useEffect(() => {
    if (!language || !ready) {
      return;
    }

    const resolvedLanguage = i18n.resolvedLanguage ?? i18n.language;
    if (resolvedLanguage !== language) {
      return;
    }

    document.title = t('module.auth.title');
  }, [language, ready, t]);

  // useEffect(() => {
  //   if (!isInitialized || !isLoggedIn) {
  //     return;
  //   }

  // const target = resolveRedirectPath();
  // if (window.location.pathname !== target) {
  //   router.replace(target);
  // }
  // }, [isInitialized, isLoggedIn, resolveRedirectPath, router]);

  const [googleTermsAccepted, setGoogleTermsAccepted] = useState(false);
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);
  const [showTermsDialog, setShowTermsDialog] = useState(false);

  const { startGoogleLogin } = useGoogleAuth({
    onSuccess: (_, redirectPath) => {
      router.replace(redirectPath);
    },
    onError: () => {
      setIsGoogleLoading(false);
    },
  });

  const doGoogleLogin = useCallback(async () => {
    try {
      setIsGoogleLoading(true);
      await startGoogleLogin({
        redirectPath: resolveRedirectPath(),
        language: language ?? undefined,
      });
    } catch (error) {
      setIsGoogleLoading(false);
    }
  }, [language, resolveRedirectPath, startGoogleLogin]);

  const handleGoogleSignIn = useCallback(async () => {
    if (!isGoogleEnabled) {
      return;
    }

    if (!googleTermsAccepted) {
      setShowTermsDialog(true);
      return;
    }

    await doGoogleLogin();
  }, [doGoogleLogin, googleTermsAccepted, isGoogleEnabled]);

  const handleTermsConfirm = useCallback(async () => {
    setGoogleTermsAccepted(true);
    setShowTermsDialog(false);
    // Auto start Google login after terms accepted
    await doGoogleLogin();
  }, [doGoogleLogin]);

  const handleTermsCancel = useCallback(() => {
    setShowTermsDialog(false);
  }, []);

  const renderLoginContent = useCallback(
    (method: LoginMethod) => {
      switch (method) {
        case 'phone':
          return (
            <PhoneLogin
              onLoginSuccess={handleAuthSuccess}
              loginContext={loginContext}
            />
          );
        case 'email':
          return <EmailLogin onLoginSuccess={handleAuthSuccess} />;
        case 'google':
          return (
            <div className='space-y-3'>
              <GoogleLoginButton
                onClick={handleGoogleSignIn}
                loading={isGoogleLoading}
                disabled={isGoogleLoading}
              />
              <TermsCheckbox
                checked={googleTermsAccepted}
                onCheckedChange={setGoogleTermsAccepted}
                disabled={isGoogleLoading}
              />
            </div>
          );
        default:
          return null;
      }
    },
    [
      handleAuthSuccess,
      handleGoogleSignIn,
      googleTermsAccepted,
      isGoogleLoading,
      loginContext,
    ],
  );

  const shouldShowTabs = availableMethods.length > 1;
  const resolvedLogo = logoSrc || logoHorizontal;

  // Show loading state until translations are ready
  if (!isI18nReady || !language) {
    return (
      <div className='min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900'>
        <div className='w-full max-w-md space-y-2'>
          <div className='flex flex-col items-center'>
            <Image
              className='dark:invert'
              src={resolvedLogo}
              alt='AI-Shifu'
              width={180}
              height={40}
              priority
            />
          </div>
          <Card>
            <CardContent className='flex items-center justify-center py-8'>
              <div className='animate-spin rounded-full h-8 w-8 border-b-2 border-primary'></div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }
  return (
    <>
      <TermsConfirmDialog
        open={showTermsDialog}
        onOpenChange={setShowTermsDialog}
        onConfirm={handleTermsConfirm}
        onCancel={handleTermsCancel}
      />
      <div className='min-h-screen flex items-center justify-center p-4'>
        <div className='w-full max-w-md space-y-2'>
          <div className='flex flex-col items-center relative'>
            <h2 className='flex items-center font-semibold pb-2 w-full justify-center'>
              <Image
                className='dark:invert'
                src={resolvedLogo}
                alt='AI-Shifu'
                width={180}
                height={40}
                priority
              />
            </h2>
            <div className='absolute top-0 right-0 z-10'>
              <LanguageSelect
                language={language}
                onSetLanguage={handleManualLanguageChange}
                variant='login'
              />
            </div>
          </div>
          <Card>
            <CardHeader>
              {authMode === 'login' && (
                <CardTitle className='text-xl text-center'>
                  {t('module.auth.title')}
                </CardTitle>
              )}
              {authMode === 'feedback' && (
                <>
                  <CardTitle className='text-xl text-center'>
                    {t('module.auth.feedback')}
                  </CardTitle>
                  <CardDescription className='text-sm text-center'>
                    {t('module.auth.feedback')}
                  </CardDescription>
                </>
              )}
            </CardHeader>

            <CardContent>
              {authMode === 'login' && (
                <div className='space-y-6'>
                  {availableMethods.length > 0 ? (
                    shouldShowTabs ? (
                      <Tabs
                        value={loginMethod}
                        onValueChange={value =>
                          setLoginMethod(value as LoginMethod)
                        }
                        className='w-full'
                      >
                        <TabsList
                          className='grid w-full'
                          style={{
                            gridTemplateColumns: `repeat(${availableMethods.length}, minmax(0, 1fr))`,
                          }}
                        >
                          {availableMethods.map(method => (
                            <TabsTrigger
                              key={method}
                              value={method}
                            >
                              {method === 'phone'
                                ? t('module.auth.phone')
                                : method === 'email'
                                  ? t('module.auth.email')
                                  : t('module.auth.googleTab')}
                            </TabsTrigger>
                          ))}
                        </TabsList>

                        {availableMethods.map(method => (
                          <TabsContent
                            key={method}
                            value={method}
                          >
                            {renderLoginContent(method)}
                          </TabsContent>
                        ))}
                      </Tabs>
                    ) : (
                      <div className='w-full'>
                        {availableMethods[0]
                          ? renderLoginContent(availableMethods[0])
                          : null}
                      </div>
                    )
                  ) : (
                    <p className='text-sm text-muted-foreground text-center'>
                      {t('module.auth.noLoginMethods')}
                    </p>
                  )}
                </div>
              )}

              {authMode === 'feedback' && (
                <FeedbackForm onComplete={handleBackToLogin} />
              )}
            </CardContent>
            <CardFooter className='flex flex-col items-center space-y-2'>
              {authMode === 'feedback' && (
                <button
                  onClick={handleBackToLogin}
                  className='text-primary hover:underline'
                >
                  {t('module.auth.backToLogin')}
                </button>
              )}
              {authMode !== 'feedback' && (
                <p className='text-sm text-muted-foreground'>
                  {t('module.auth.problem')}
                  <button
                    onClick={handleFeedback}
                    className='hover:underline'
                  >
                    {t('module.auth.submitFeedback')}
                  </button>
                </p>
              )}
            </CardFooter>
          </Card>
        </div>
      </div>
    </>
  );
}
