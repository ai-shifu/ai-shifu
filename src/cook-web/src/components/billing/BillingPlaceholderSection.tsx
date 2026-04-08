import React from 'react';
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';

type BillingPlaceholderSectionProps = {
  title: string;
  description: string;
};

export function BillingPlaceholderSection({
  title,
  description,
}: BillingPlaceholderSectionProps) {
  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader>
        <CardTitle className='text-lg text-slate-900'>{title}</CardTitle>
        <CardDescription className='leading-6'>{description}</CardDescription>
      </CardHeader>
    </Card>
  );
}
