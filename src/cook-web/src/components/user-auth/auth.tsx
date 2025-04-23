'use client'

import type React from 'react'

import { useState } from 'react'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { LoginForm } from '@/components/user-auth/login-form'
import { RegisterForm } from '@/components/user-auth/register-form'
import { ForgotPasswordForm } from '@/components/user-auth/forgot-password-form'
import { FeedbackForm } from '@/components/user-auth/feedback-form'
import { Card, CardContent } from '@/components/ui/card'

type AuthFormType = 'login' | 'register' | 'forgotPassword' | 'feedback'

interface AuthProps {
  showMode?: 'card' | 'dialog'
  defaultForm?: AuthFormType
  onSuccess?: () => void
}

export function Auth ({
  showMode = 'card',
  defaultForm = 'login',
  onSuccess
}: AuthProps) {
  const [open, setOpen] = useState(false)
  const [currentForm, setCurrentForm] = useState<AuthFormType>(defaultForm)

  const handleSuccess = () => {
    if (onSuccess) {
      onSuccess()
    }
    setOpen(false)
  }

  const renderForm = () => {
    switch (currentForm) {
      case 'login':
        return (
          <LoginForm
            isDialog
            onSuccess={handleSuccess}
            onRegisterClick={() => setCurrentForm('register')}
            onForgotPasswordClick={() => setCurrentForm('forgotPassword')}
            onFeedbackClick={() => setCurrentForm('feedback')}
          />
        )
      case 'register':
        return (
          <RegisterForm
            isDialog
            onSuccess={handleSuccess}
            onLoginClick={() => setCurrentForm('login')}
            onFeedbackClick={() => setCurrentForm('feedback')}
          />
        )
      case 'forgotPassword':
        return (
          <ForgotPasswordForm
            isDialog
            onSuccess={() => setCurrentForm('login')}
            onLoginClick={() => setCurrentForm('login')}
          />
        )
      case 'feedback':
        return (
          <FeedbackForm
            isDialog
            onSuccess={handleSuccess}
            onLoginClick={() => setCurrentForm('login')}
          />
        )
      default:
        return <LoginForm isDialog onSuccess={handleSuccess} />
    }
  }

  return (
    <>
      {showMode === 'card' ? (
        <Card>
          <CardContent>{renderForm()}</CardContent>
        </Card>
      ) : (
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent className='sm:max-w-[425px] md:max-w-[500px] lg:max-w-[550px]'>
            {renderForm()}
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}
