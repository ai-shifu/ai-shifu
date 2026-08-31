'use client';

import type { UserInfo } from '@/c-types';
import { VerificationCodeLogin } from '@/components/auth/VerificationCodeLogin';
import type { ReferralLoginMetadata } from '@/types/referral';

interface EmailLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
  loginContext?: string;
  courseId?: string;
  referralMetadata?: ReferralLoginMetadata;
}

export function EmailLogin(props: EmailLoginProps) {
  return (
    <VerificationCodeLogin
      mode='email'
      {...props}
    />
  );
}
