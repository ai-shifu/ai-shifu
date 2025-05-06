'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
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
import { setToken } from '@/local/local'
import LanguageSelect from '@/components/language-select'
import { useTranslation } from 'react-i18next';
import i18n from '@/i18n';
/**
 * Renders a multi-mode authentication page with support for login, registration, password recovery, and feedback, featuring dynamic language selection and internationalized UI.
 *
 * The component manages authentication and registration flows via tabbed interfaces for phone and email methods, and allows users to switch between modes. All user-facing text is localized, and users can change the interface language using a language selector. Upon successful authentication or registration, users are redirected to the main page.
 *
 * @remark The authentication token is cleared on mount to ensure a fresh session.
 */
export default function AuthPage () {
  const router = useRouter()
  const [authMode, setAuthMode] = useState<
    'login' | 'register' | 'forgot-password' | 'feedback'
  >('login')
  const [loginMethod, setLoginMethod] = useState<'phone' | 'password'>('phone')
  const [registerMethod, setRegisterMethod] = useState<'phone' | 'email'>(
    'phone'
  )
  const [language, setLanguage] = useState('zh-CN')
  const handleAuthSuccess = () => {
    router.push('/main')
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
          <h2 className='text-purple-600 flex items-center font-semibold pb-2  w-full justify-center'>
            <Image
              className='dark:invert'
              src='/logo.svg'
              alt='AI-Shifu'
              width={140}
              height={30}
              priority
            />

          <div className='absolute top-0 right-0'>
          <LanguageSelect language={language} onSetLanguage={setLanguage} variant='circle' />
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
                  <TabsTrigger value='phone'>{t('login.phone')}</TabsTrigger>
                  <TabsTrigger value='email'>{t('login.email')}</TabsTrigger>
                </TabsList>

                <TabsContent value='phone'>
                  <PhoneRegister onRegisterSuccess={handleAuthSuccess} />
                </TabsContent>

                <TabsContent value='email'>
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
                    {t('login.login')}
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
