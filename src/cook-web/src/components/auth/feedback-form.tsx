'use client';

import type React from 'react';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import apiService from '@/api';
import { isValidEmail } from '@/lib/validators';

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

  const validateEmail = (email: string) => {
    if (!email) {
      setEmailError('请输入邮箱');
      return false;
    }

    if (!isValidEmail(email)) {
      setEmailError('请输入有效的邮箱地址');
      return false;
    }

    setEmailError('');
    return true;
  };

  const validateContent = (content: string) => {
    if (!content) {
      setContentError('请输入反馈内容');
      return false;
    }

    if (content.length < 10) {
      setContentError('反馈内容至少10个字符');
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
          title: '反馈提交成功',
          description: '感谢您的反馈，我们会尽快处理',
        });
        onComplete();
      } else {
        toast({
          title: '提交失败',
          description: response.msg || '请稍后重试',
          variant: 'destructive',
        });
      }
    } catch (error: any) {
      toast({
        title: '提交失败',
        description: error.message || '网络错误，请稍后重试',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label
          htmlFor="feedback-email"
          className={emailError ? 'text-red-500' : ''}
        >
          您的邮箱
        </Label>
        <Input
          id="feedback-email"
          type="email"
          placeholder="请输入您的邮箱"
          value={email}
          onChange={handleEmailChange}
          disabled={isLoading}
          className={
            emailError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {emailError && <p className="text-xs text-red-500">{emailError}</p>}
      </div>
      <div className="space-y-2">
        <Label
          htmlFor="feedback-content"
          className={contentError ? 'text-red-500' : ''}
        >
          反馈内容
        </Label>
        <Textarea
          id="feedback-content"
          placeholder="请详细描述您遇到的问题或建议"
          rows={5}
          value={content}
          onChange={handleContentChange}
          disabled={isLoading}
          className={
            contentError ? 'border-red-500 focus-visible:ring-red-500' : ''
          }
        />
        {contentError && <p className="text-xs text-red-500">{contentError}</p>}
      </div>
      <Button
        className="w-full h-8"
        onClick={handleSubmit}
        disabled={isLoading}
      >
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
        提交反馈
      </Button>
    </div>
  );
}
