'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle
} from '@/components/ui/card'
import { PhoneLogin } from '@/components/auth/phone-login'
import { EmailLogin } from '@/components/auth/email-login'
import { PhoneRegister } from '@/components/auth/phone-register'
import { EmailRegister } from '@/components/auth/email-register'
import { ForgotPasswordForm } from '@/components/auth/forgot-password-form'
import { FeedbackForm } from '@/components/auth//feedback-form'
import Image from 'next/image'
import logoHorizontal from '@/c-assets/logos/ai-shifu-logo-horizontal.png'
import { setToken } from '@/local/local'
import LanguageSelect from '@/components/language-select'
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
import { browserLanguage } from '@/i18n';

import { useUserStore } from '@/c-store/useUserStore';
import type { UserInfo } from '@/c-types'

export default function AuthPage () {
  const router = useRouter()
  const [authMode, setAuthMode] = useState<
    'login' | 'register' | 'forgot-password' | 'feedback'
  >('login')
  const [loginMethod, setLoginMethod] = useState<'phone' | 'password'>('phone')
  const [registerMethod, setRegisterMethod] = useState<'phone' | 'email'>(
    'phone'
  )
  const [language, setLanguage] = useState(browserLanguage)
  
  /**
   * Sync user login information to the "web(c)".
   * TODO:
   *   - Consolidate and synchronize the `hasLogin` and `hasCheckLogin` logic.
   */
  const updateUserInfo = useUserStore((state) => state.updateUserInfo);
  const _setHasLogin = useUserStore((state) => state._setHasLogin);
  
  const searchParams = useSearchParams()
  const handleAuthSuccess = (userInfo: UserInfo) => {
    updateUserInfo(userInfo)
    _setHasLogin(true)
    
    let redirect = searchParams.get('redirect')
    if (!redirect || redirect.charAt(0) !== '/') {
      redirect = '/main'
    }
    // Using push for navigation keeps a history, so when users click the back button, they'll return to the login page.
    // router.push('/main')
    router.replace(redirect)
  }

  const handleForgotPassword = () => {
    setAuthMode('forgot-password')
  }

  const handleFeedback = () => {
    setAuthMode('feedback')
  }

  const handleBackToLogin = () => {
    setAuthMode('login')
  }

  const { t } = useTranslation();
  useEffect(() => {
    setToken('')
  }, [])

  useEffect(() => {
    i18n.changeLanguage(language)

  }, [language])
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
          <LanguageSelect language={language} onSetLanguage={setLanguage} variant='login' />
        </div>
        </h2>
        </div>
        <Card>
          <CardHeader>
            {authMode === 'login' && (
              <>
                <CardTitle className='text-xl text-center'>{t('login.title')}</CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('login.description')}
                </CardDescription>
              </>
            )}
            {authMode === 'register' && (
              <>
                <CardTitle className='text-xl text-center'>{t('login.register')}</CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('login.register-description')}
                </CardDescription>
              </>
            )}
            {authMode === 'forgot-password' && (
              <>
                <CardTitle className='text-xl text-center'>{t('login.forgot-password')}</CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('login.forgot-password')}
                </CardDescription>
              </>
            )}
            {authMode === 'feedback' && (
              <>
                <CardTitle className='text-xl text-center'>{t('login.feedback')}</CardTitle>
                <CardDescription className='text-sm text-center'>
                  {t('login.feedback')}
                </CardDescription>
              </>
            )}

          </CardHeader>

          <CardContent>
            {authMode === 'login' && (
              <Tabs
                value={loginMethod}
                onValueChange={value =>
                  setLoginMethod(value as 'phone' | 'password')
                }
                className='w-full'
              >
                <TabsList className='grid w-full grid-cols-2'>
                  <TabsTrigger value='phone'>{t('login.phone')}</TabsTrigger>
                  <TabsTrigger value='password'>{t('login.email')}</TabsTrigger>
                </TabsList>

                <TabsContent value='phone'>
                  <PhoneLogin onLoginSuccess={handleAuthSuccess} />
                </TabsContent>

                <TabsContent value='password'>
                  <EmailLogin
                    onLoginSuccess={handleAuthSuccess}
                    onForgotPassword={handleForgotPassword}
                  />
                </TabsContent>
              </Tabs>
            )}

            {authMode === 'register' && (
              <Tabs
                value={registerMethod}
                onValueChange={value =>
                  setRegisterMethod(value as 'phone' | 'email')
                }
                className='w-full'
              >
                <TabsList className='grid w-full grid-cols-2'>
                  <TabsTrigger value='phone'>{t('login.phone-register')}</TabsTrigger>
                  <TabsTrigger value='email'>{t('login.email-register')}</TabsTrigger>
                </TabsList>

                <TabsContent value='phone'>
                  {/* TODO: FIXME */}
                  {/* @ts-expect-error EXPECT */}
                  <PhoneRegister onRegisterSuccess={handleAuthSuccess} />
                </TabsContent>

                <TabsContent value='email'>
                  {/* TODO: FIXME */}
                  {/* @ts-expect-error EXPECT */}
                  <EmailRegister onRegisterSuccess={handleAuthSuccess} />
                </TabsContent>
              </Tabs>
            )}

            {authMode === 'forgot-password' && (
              <ForgotPasswordForm onComplete={handleBackToLogin} />
            )}

            {authMode === 'feedback' && (
              <FeedbackForm onComplete={handleBackToLogin} />
            )}
          </CardContent>
          <CardFooter className='flex flex-col items-center space-y-2'>
            {authMode === 'login' && (
              <>
                <p className='text-sm text-muted-foreground'>
                  {t('login.no-account')}
                  <button
                    onClick={() => setAuthMode('register')}
                    className='text-primary hover:underline'
                  >
                    {t('login.register')}
                  </button>
                </p>
              </>
            )}
            {authMode === 'register' && (
              <>
                <p className='text-sm text-muted-foreground'>
                  {t('login.has-account')}
                  <button
                    onClick={() => setAuthMode('login')}
                    className='text-primary hover:underline'
                  >
                    {t('login.login-now')}
                  </button>
                </p>
              </>
            )}
            {(authMode === 'forgot-password' || authMode === 'feedback') && (
              <button
                onClick={handleBackToLogin}
                className='text-primary hover:underline'
              >
                {t('login.back-to-login')}
              </button>
            )}
            {authMode !== 'feedback' && (
              <p className='text-sm text-muted-foreground'>
                {t('login.problem')}
                <button
                  onClick={handleFeedback}
                  className='text-primary hover:underline'
                >
                  {t('login.submit-feedback')}
                </button>
              </p>
            )}
          </CardFooter>
        </Card>



      </div>
    </div>
  )
}
