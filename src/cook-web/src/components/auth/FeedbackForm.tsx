'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { isValidEmail } from '@/lib/validators';
import { useTranslation } from 'react-i18next';

interface FeedbackFormProps {
  onComplete: () => void;
}

export function FeedbackForm({ onComplete }: FeedbackFormProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [content, setContent] = useState('');
  const [emailError, setEmailError] = useState('');
  const [contentError, setContentError] = useState('');
  const { t } = useTranslation();
  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError(t('auth.emailEmpty'));
      return false;
    }

    if (!isValidEmail(email)) {
      setEmailError(t('auth.emailError'));
      return false;
    }

    setEmailError('');
    return true;
  };

  const validateContent = (content: string) => {
    if (!content) {
      setContentError(t('auth.contentEmpty'));
      return false;
    }

    if (content.length < 10) {
      setContentError(t('auth.contentError'));
      return false;
    }

    setContentError('');
    return true;
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setEmail(value);
    if (value) {
      validateEmail(value);
    } else {
      setEmailError('');
    }
  };

  const handleContentChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setContent(value);
    if (value) {
      validateContent(value);
    } else {
      setContentError('');
    }
  };

  const handleSubmit = async () => {
    const isEmailValid = validateEmail(email);
    const isContentValid = validateContent(content);

    if (!isEmailValid || !isContentValid) {
      return;
    }

    try {
      setIsLoading(true);

      const response = await apiService.submitFeedback({
        mail: email,
        feedback: content,
      });
      if (response.code) {
        return;
      }
      if (response) {
        toast({
          title: t('auth.feedbackSubmitted'),
          description: t('auth.feedbackSubmittedDescription'),
        });
        onComplete();
      } else {
        toast({
          title: t('common.submitFailed'),
          description: response.msg || t('common.networkError'),
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: t('common.submitFailed'),
        description: error.message || t('common.networkError'),
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className='space-y-4'>
      <div className='space-y-2'>
        <Label
          htmlFor='feedback-email'
          className={emailError ? 'text-red-500' : ''}
        >
          {t('auth.yourEmail')}
        </Label>
        <Input
          id='feedback-email'
          type='email'
          placeholder={t('auth.emailPlaceholder')}
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
          {t('auth.feedbackContent')}
        </Label>
        <Textarea
          id='feedback-content'
          placeholder={t('auth.contentPlaceholder')}
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
      <Button
        className='w-full h-8'
        onClick={handleSubmit}
        disabled={isLoading}
      >
        {isLoading ? <Loader2 className='h-4 w-4 animate-spin mr-2' /> : null}
        {t('auth.submitFeedback')}
      </Button>
    </div>
  );
}
