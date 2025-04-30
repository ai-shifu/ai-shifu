'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { PhoneLogin } from '@/components/auth/phone-login';
import { EmailLogin } from '@/components/auth/email-login';
import { PhoneRegister } from '@/components/auth/phone-register';
import { EmailRegister } from '@/components/auth/email-register';
import { ForgotPasswordForm } from '@/components/auth/forgot-password-form';
import { FeedbackForm } from '@/components/auth//feedback-form';
import Image from 'next/image';
import { setToken } from '@/local/local';

export default function AuthPage() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<
    'login' | 'register' | 'forgot-password' | 'feedback'
  >('login');
  const [loginMethod, setLoginMethod] = useState<'phone' | 'password'>('phone');
  const [registerMethod, setRegisterMethod] = useState<'phone' | 'email'>(
    'phone',
  );

  const handleAuthSuccess = () => {
    router.push('/main');
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

  useEffect(() => {
    setToken('');
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
      <div className="w-full max-w-md space-y-2">
        <div className="flex flex-col items-center">
          <h2 className="text-purple-600 flex items-center font-semibold pb-2">
            <Image
              className="dark:invert"
              src="/logo.svg"
              alt="AI-Shifu"
              width={140}
              height={30}
              priority
            />
          </h2>
        </div>
        <Card>
          <CardHeader>
            {authMode === 'login' && (
              <>
                <CardTitle className="text-xl text-center">用户登录</CardTitle>
                <CardDescription className="text-sm text-center">
                  请选择登录方式
                </CardDescription>
              </>
            )}
            {authMode === 'register' && (
              <>
                <CardTitle className="text-xl text-center">用户注册</CardTitle>
                <CardDescription className="text-sm text-center">
                  请选择注册方式
                </CardDescription>
              </>
            )}
            {authMode === 'forgot-password' && (
              <>
                <CardTitle className="text-xl text-center">忘记密码</CardTitle>
                <CardDescription className="text-sm text-center">
                  请输入您的邮箱并获取验证码
                </CardDescription>
              </>
            )}
            {authMode === 'feedback' && (
              <>
                <CardTitle className="text-xl text-center">提交反馈</CardTitle>
                <CardDescription className="text-sm text-center">
                  请告诉我们您遇到的问题或建议
                </CardDescription>
              </>
            )}
          </CardHeader>
          <CardContent>
            {authMode === 'login' && (
              <Tabs
                value={loginMethod}
                onValueChange={(value) =>
                  setLoginMethod(value as 'phone' | 'password')
                }
                className="w-full"
              >
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="phone">手机号登录</TabsTrigger>
                  <TabsTrigger value="password">邮箱登录</TabsTrigger>
                </TabsList>

                <TabsContent value="phone">
                  <PhoneLogin onLoginSuccess={handleAuthSuccess} />
                </TabsContent>

                <TabsContent value="password">
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
                onValueChange={(value) =>
                  setRegisterMethod(value as 'phone' | 'email')
                }
                className="w-full"
              >
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="phone">手机号注册</TabsTrigger>
                  <TabsTrigger value="email">邮箱注册</TabsTrigger>
                </TabsList>

                <TabsContent value="phone">
                  <PhoneRegister onRegisterSuccess={handleAuthSuccess} />
                </TabsContent>

                <TabsContent value="email">
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
          <CardFooter className="flex flex-col items-center space-y-2">
            {authMode === 'login' && (
              <>
                <p className="text-sm text-muted-foreground">
                  还没有账号?{' '}
                  <button
                    onClick={() => setAuthMode('register')}
                    className="text-primary hover:underline"
                  >
                    立即注册
                  </button>
                </p>
              </>
            )}
            {authMode === 'register' && (
              <>
                <p className="text-sm text-muted-foreground">
                  已有账号?{' '}
                  <button
                    onClick={() => setAuthMode('login')}
                    className="text-primary hover:underline"
                  >
                    立即登录
                  </button>
                </p>
              </>
            )}
            {(authMode === 'forgot-password' || authMode === 'feedback') && (
              <button
                onClick={handleBackToLogin}
                className="text-primary hover:underline"
              >
                返回登录
              </button>
            )}
            {authMode !== 'feedback' && (
              <p className="text-sm text-muted-foreground">
                登录遇到问题?{' '}
                <button
                  onClick={handleFeedback}
                  className="text-primary hover:underline"
                >
                  提交反馈
                </button>
              </p>
            )}
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
