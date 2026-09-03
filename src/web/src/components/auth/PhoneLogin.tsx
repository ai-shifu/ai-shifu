'use client';

import type { UserInfo } from '@/c-types';
import { VerificationCodeLogin } from '@/components/auth/VerificationCodeLogin';
import type { ReferralLoginMetadata } from '@/types/referral';

interface PhoneLoginProps {
  onLoginSuccess: (userInfo: UserInfo) => void;
  loginContext?: string;
  courseId?: string;
  referralMetadata?: ReferralLoginMetadata;
}

export function PhoneLogin(props: PhoneLoginProps) {
  return (
    <VerificationCodeLogin
      mode='phone'
      {...props}
    />
  );
}
