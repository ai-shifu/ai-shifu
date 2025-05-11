'use client'

import type React from 'react'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/hooks/use-toast'
import { Loader2 } from 'lucide-react'
import apiService from '@/api'
import { isValidEmail } from '@/lib/validators'
import { useTranslation } from 'react-i18next';

interface FeedbackFormProps {
  onComplete: () => void
}

/**
 * Renders a user feedback form with email and content fields, including validation and submission handling.
 *
 * Displays validation errors for invalid input and shows toast notifications for submission success or failure. Invokes {@link onComplete} after successful feedback submission.
 *
 * @param onComplete - Callback function called after successful feedback submission.
 */
export function FeedbackForm ({ onComplete }: FeedbackFormProps) {
  const { toast } = useToast()
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [content, setContent] = useState('')
  const [emailError, setEmailError] = useState('')
  const [contentError, setContentError] = useState('')
  const { t } = useTranslation();
  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('login.email-error'))
      return false
    }

    if (!isValidEmail(email)) {
      setEmailError(t('login.email-error'))
      return false
    }

    setEmailError('')
    return true
  }

  const validateContent = (content: string) => {
    if (!content) {
      setContentError(t('login.content-error'))
      return false
    }

    if (content.length < 10) {
      setContentError(t('login.content-error'))
      return false
    }

    setContentError('')
    return true
  }

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    setEmail(value)
    if (value) {
      validateEmail(value)
    } else {
      setEmailError('')
    }
  }

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setContent(value)
    if (value) {
      validateContent(value)
    } else {
      setContentError('')
    }
  }

  const handleSubmit = async () => {
    const isEmailValid = validateEmail(email)
    const isContentValid = validateContent(content)

    if (!isEmailValid || !isContentValid) {
      return
    }

    try {
      setIsLoading(true)

      const response = await apiService.submitFeedback({
        mail: email,
        feedback: content
      })
      if (response.code) {
        return
      }
      if (response) {
        toast({
          title: t('login.feedback-submitted'),
          description: t('login.thank-you-for-your-feedback')
        })
        onComplete()
      } else {
        toast({
          title: t('login.submit-failed'),
          description: response.msg || t('login.please-try-again-later'),
          variant: 'destructive'
        })
      }
    } catch (error: any) {
      toast({
        title: t('login.submit-failed'),
        description: error.message || t('login.network-error'),
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='feedback-email'
          className={emailError ? 'text-red-500' : ''}
        >
          {t('login.your-email')}
        </Label>
        <Input
          id='feedback-email'
          type='email'
          placeholder={t('login.email-placeholder')}
          value={email}
          onChange={handleEmailChange}
          disabled={isLoading}
          className={
            emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {emailError && <p className='text-xs text-red-500'>{emailError}</p>}
      </div>
      <div className='space-y-2'>
        <Label
          htmlFor='feedback-content'
          className={contentError ? 'text-red-500' : ''}
        >
          {t('login.feedback-content')}
        </Label>
        <Textarea
          id='feedback-content'
          placeholder={t('login.content-placeholder')}
          rows={5}
          value={content}
          onChange={handleContentChange}
          disabled={isLoading}
          className={
            contentError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {contentError && <p className='text-xs text-red-500'>{contentError}</p>}
      </div>
      <Button className='w-full h-8' onClick={handleSubmit} disabled={isLoading}>
        {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('login.submit-feedback')}
      </Button>
    </div>
  )
}
