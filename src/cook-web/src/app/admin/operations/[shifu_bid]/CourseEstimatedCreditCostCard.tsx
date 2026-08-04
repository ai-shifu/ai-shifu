'use client';

import { useTranslation } from 'react-i18next';
import { formatAdminCredits } from '@/app/admin/lib/numberFormat';
import { Badge } from '@/components/ui/Badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card';
import { cn } from '@/lib/utils';
import type {
  AdminOperationEstimatedCreditComponent,
  AdminOperationEstimatedCreditCost,
  AdminOperationEstimatedCreditMode,
} from '../operation-course-types';

type CourseEstimatedCreditCostCardProps = {
  estimate?: AdminOperationEstimatedCreditCost | null;
  locale: string;
};

const EMPTY_COMPONENT: AdminOperationEstimatedCreditComponent = {
  min: 0,
  max: 0,
  model: '',
  model_label: '',
  multiplier: null,
};

const EMPTY_ESTIMATE: AdminOperationEstimatedCreditCost = {
  read: {
    min: 0,
    max: 0,
    llm: EMPTY_COMPONENT,
    tts: null,
    enabled: null,
  },
  listen: {
    min: 0,
    max: 0,
    llm: EMPTY_COMPONENT,
    tts: null,
    enabled: null,
  },
  classroom: {
    min: 0,
    max: 0,
    llm: EMPTY_COMPONENT,
    tts: null,
    enabled: null,
  },
  assumptions: {
    visible_lesson_count: 0,
    prompt_char_count: 0,
    content_char_count: 0,
    calculated_at: '',
  },
};

type ModeConfig = {
  key: 'read' | 'listen' | 'classroom';
  label: string;
  mode: AdminOperationEstimatedCreditMode;
  showBreakdown: boolean;
};

const formatRange = (
  min: number,
  max: number,
  locale: string,
  creditUnit: string,
): string =>
  `${formatAdminCredits(min, locale)} - ${formatAdminCredits(
    max,
    locale,
  )} ${creditUnit}`;

const formatComponentMeta = (
  type: string,
  component: AdminOperationEstimatedCreditComponent,
  unknownModel: string,
): string => {
  const model = component.model_label || component.model || unknownModel;
  return [type, model, component.multiplier].filter(Boolean).join(' · ');
};

export default function CourseEstimatedCreditCostCard({
  estimate,
  locale,
}: CourseEstimatedCreditCostCardProps) {
  const { t } = useTranslation('module.operationsCourse');
  const hasEstimate = Boolean(estimate);
  const safeEstimate = estimate ?? EMPTY_ESTIMATE;
  const creditUnit = t('detail.estimatedCreditCost.creditUnit');
  const unknownModel = t('detail.estimatedCreditCost.unknownModel');
  const modes: ModeConfig[] = [
    {
      key: 'read',
      label: t('detail.estimatedCreditCost.read'),
      mode: safeEstimate.read,
      showBreakdown: false,
    },
    {
      key: 'listen',
      label: t('detail.estimatedCreditCost.listen'),
      mode: safeEstimate.listen,
      showBreakdown: true,
    },
    {
      key: 'classroom',
      label: t('detail.estimatedCreditCost.classroom'),
      mode: safeEstimate.classroom,
      showBreakdown: false,
    },
  ];

  return (
    <Card>
      <CardHeader className='p-5 pb-3'>
        <div className='flex flex-col gap-1'>
          <CardTitle className='text-base font-semibold tracking-normal'>
            {t('detail.estimatedCreditCost.title')}
          </CardTitle>
          <CardDescription>
            {t('detail.estimatedCreditCost.description')}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className='p-5 pt-0'>
        <div className='grid gap-3 md:grid-cols-3'>
          {modes.map(({ key, label, mode, showBreakdown }) => {
            const llmLabel = t('detail.estimatedCreditCost.llm');
            const ttsLabel = t('detail.estimatedCreditCost.tts');
            const llmBreakdown = `${llmLabel}：${formatAdminCredits(
              mode.llm.min,
              locale,
            )} - ${formatAdminCredits(mode.llm.max, locale)}`;
            const ttsBreakdown = mode.tts
              ? `${ttsLabel}：${formatAdminCredits(mode.tts.min, locale)} - ${formatAdminCredits(
                  mode.tts.max,
                  locale,
                )}`
              : '';

            return (
              <section
                key={key}
                className={cn('rounded-lg border bg-stone-50/70 p-3')}
              >
                <div className='flex items-center justify-between gap-3'>
                  <h3 className='text-sm font-medium text-foreground'>
                    {label}
                  </h3>
                  {hasEstimate && mode.enabled === false ? (
                    <Badge
                      variant='outline'
                      className='border-amber-300 bg-white px-2 py-0 text-amber-700'
                    >
                      {t('detail.estimatedCreditCost.disabled')}
                    </Badge>
                  ) : null}
                </div>
                <div className='mt-2 text-xl font-semibold tracking-tight text-foreground'>
                  {hasEstimate
                    ? formatRange(mode.min, mode.max, locale, creditUnit)
                    : '--'}
                </div>
                <div className='mt-2 space-y-1 text-xs'>
                  {hasEstimate && showBreakdown ? (
                    <>
                      <p className='text-foreground'>{llmBreakdown}</p>
                      <p className='text-muted-foreground'>
                        {formatComponentMeta(llmLabel, mode.llm, unknownModel)}
                      </p>
                      {mode.tts ? (
                        <>
                          <p className='pt-1 text-foreground'>{ttsBreakdown}</p>
                          <p className='text-muted-foreground'>
                            {formatComponentMeta(
                              ttsLabel,
                              mode.tts,
                              unknownModel,
                            )}
                          </p>
                        </>
                      ) : null}
                    </>
                  ) : null}
                  {hasEstimate && !showBreakdown ? (
                    <p className='text-muted-foreground'>
                      {formatComponentMeta(llmLabel, mode.llm, unknownModel)}
                    </p>
                  ) : null}
                </div>
              </section>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
