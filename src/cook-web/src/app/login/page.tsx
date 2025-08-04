'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { PhoneLogin } from '@/components/auth/PhoneLogin';
import { EmailLogin } from '@/components/auth/EmailLogin';
import { EmailRegister } from '@/components/auth/EmailRegister';
import { ForgotPasswordForm } from '@/components/auth/ForgotPasswordForm';
import { FeedbackForm } from '@/components/auth/FeedbackForm';
import Image from 'next/image';
import logoHorizontal from '@/c-assets/logos/ai-shifu-logo-horizontal.png';
import LanguageSelect from '@/components/language-select';
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { browserLanguage } from '@/i18n';
import { environment } from '@/config/environment';

export default function AuthPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<
    'login' | 'register' | 'forgot-password' | 'feedback'
  >('login');

  // Get login methods from environment configuration
  const enabledMethods = environment.loginMethodsEnabled;
  const defaultMethod = environment.defaultLoginMethod;

  const isPhoneEnabled = enabledMethods.includes('phone');
  const isEmailEnabled = enabledMethods.includes('email');

  const [loginMethod, setLoginMethod] = useState<'phone' | 'email'>(
    defaultMethod as 'phone' | 'email',
  );
  const [language, setLanguage] = useState(browserLanguage);

  const searchParams = useSearchParams();
  const handleAuthSuccess = () => {
    let redirect = searchParams.get('redirect');
    if (!redirect || redirect.charAt(0) !== '/') {
      redirect = '/c';
    }
    // Using push for navigation keeps a history, so when users click the back button, they'll return to the login page.
    // router.push('/main')
    router.replace(redirect);
  };

  const handleForgotPassword = () => {
    setAuthMode('forgot-password');
  };

  const handleFeedback = () => {
    setAuthMode('feedback');
  };

  const handleBackToLogin = () => {
    setAuthMode('login');
  };

  const { t } = useTranslation();

  useEffect(() => {
    i18n.changeLanguage(language);
  }, [language]);
  return (
    <div className='min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4'>
      <div className='w-full max-w-md space-y-2'>
        <div className='flex flex-col items-center relative'>
          <h2 className='text-primary flex items-center font-semibold pb-2  w-full justify-center'>
            <Image
              className='dark:invert'
              src={logoHorizontal}
              alt='AI-Shifu'
              width={180}
              height={40}
              priority
            />

            <div className='absolute top-0 right-0'>
              <LanguageSelect
                language={language}
                onSetLanguage={setLanguage}
                variant='login'
              />
            </div>
          </h2>
        </div>
        <Card>
          <CardHeader>
            {authMode === 'login' && (
              <>
                <CardTitle className='text-xl text-center'>
                  {t('auth.title')}
                </CardTitle>
              </>
            )}
            {authMode === 'register' && (
              <>
                <CardTitle className='text-xl text-center'>
                  {t('auth.register')}
                </CardTitle>
              </>
            )}
            {authMode === 'forgot-password' && (
              <>
                <CardTitle className='text-xl text-center'>
                  {t('auth.forgot-password')}
                </CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('auth.forgot-password')}
                </CardDescription>
              </>
            )}
            {authMode === 'feedback' && (
              <>
                <CardTitle className='text-xl text-center'>
                  {t('auth.feedback')}
                </CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('auth.feedback')}
                </CardDescription>
              </>
            )}
          </CardHeader>

          <CardContent>
            {authMode === 'login' && (
              <>
                {enabledMethods.length > 1 ? (
                  <Tabs
                    value={loginMethod}
                    onValueChange={value =>
                      setLoginMethod(value as 'phone' | 'email')
                    }
                    className='w-full'
                  >
                    <TabsList className={'grid w-full grid-cols-2'}>
                      {isPhoneEnabled && (
                        <TabsTrigger value='phone'>
                          {t('auth.phone')}
                        </TabsTrigger>
                      )}
                      {isEmailEnabled && (
                        <TabsTrigger value='email'>
                          {t('auth.email')}
                        </TabsTrigger>
                      )}
                    </TabsList>

                    {isPhoneEnabled && (
                      <TabsContent value='phone'>
                        <PhoneLogin onLoginSuccess={handleAuthSuccess} />
                      </TabsContent>
                    )}

                    {isEmailEnabled && (
                      <TabsContent value='email'>
                        <EmailLogin
                          onLoginSuccess={handleAuthSuccess}
                          onForgotPassword={handleForgotPassword}
                        />
                      </TabsContent>
                    )}
                  </Tabs>
                ) : (
                  // Single method, no tabs needed
                  <div className='w-full'>
                    {isPhoneEnabled && (
                      <PhoneLogin onLoginSuccess={handleAuthSuccess} />
                    )}
                    {isEmailEnabled && (
                      <EmailLogin
                        onLoginSuccess={handleAuthSuccess}
                        onForgotPassword={handleForgotPassword}
                      />
                    )}
                  </div>
                )}
              </>
            )}

            {authMode === 'register' && (
              <>
                {/* Only email registration is needed since phone now auto-registers */}
                {isEmailEnabled ? (
                  <div className='w-full'>
                    <EmailRegister onRegisterSuccess={handleAuthSuccess} />
                  </div>
                ) : (
                  <p className='text-center text-muted-foreground'>
                    {t('auth.no-registration-method')}
                  </p>
                )}
              </>
            )}

            {authMode === 'forgot-password' && (
              <ForgotPasswordForm onComplete={handleBackToLogin} />
            )}

            {authMode === 'feedback' && (
              <FeedbackForm onComplete={handleBackToLogin} />
            )}
          </CardContent>
          <CardFooter className='flex flex-col items-center space-y-2'>
            {authMode === 'login' && isEmailEnabled && (
              <>
                <p className='text-sm text-muted-foreground'>
                  {t('auth.no-account')}
                  <button
                    onClick={() => setAuthMode('register')}
                    className='text-primary hover:underline'
                  >
                    {t('auth.register')}
                  </button>
                </p>
              </>
            )}
            {authMode === 'register' && (
              <>
                <p className='text-sm text-muted-foreground'>
                  {t('auth.has-account')}
                  <button
                    onClick={() => setAuthMode('login')}
                    className='text-primary hover:underline'
                  >
                    {t('auth.login-now')}
                  </button>
                </p>
              </>
            )}
            {(authMode === 'forgot-password' || authMode === 'feedback') && (
              <button
                onClick={handleBackToLogin}
                className='text-primary hover:underline'
              >
                {t('auth.back-to-login')}
              </button>
            )}
            {authMode !== 'feedback' && (
              <p className='text-sm text-muted-foreground'>
                {t('auth.problem')}
                <button
                  onClick={handleFeedback}
                  className='text-primary hover:underline'
                >
                  {t('auth.submit-feedback')}
                </button>
              </p>
            )}
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
