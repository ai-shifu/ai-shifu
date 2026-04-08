import React from 'react';
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';

type BillingMetricCardProps = {
  label: string;
  value: string;
};

export function BillingMetricCard({ label, value }: BillingMetricCardProps) {
  return (
    <Card className='border-slate-200 bg-white/90 shadow-[0_10px_30px_rgba(15,23,42,0.06)]'>
      <CardHeader className='pb-3'>
        <CardDescription>{label}</CardDescription>
        <CardTitle className='text-3xl font-semibold tracking-tight text-slate-900'>
          {value}
        </CardTitle>
      </CardHeader>
    </Card>
  );
}
