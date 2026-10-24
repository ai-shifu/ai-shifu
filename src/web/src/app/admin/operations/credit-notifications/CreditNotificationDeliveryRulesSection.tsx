import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import type { AdminOperationCreditNotificationPolicy } from '../operation-credit-notification-types';
import { cn } from '@/lib/utils';
import { CreditNotificationConfigSection as ConfigSection } from './CreditNotificationFormPrimitives';
import {
  BudgetCard,
  FrequencyCard,
  QuietHoursCard,
  SoftlimitCard,
} from './CreditNotificationDeliveryRuleCards';
import type { UpdatePolicy } from './useCreditNotificationConfigTabState';

export type CreditNotificationDeliveryRulesSectionProps = {
  contactMode: 'email' | 'phone';
  policy: AdminOperationCreditNotificationPolicy;
  updatePolicy: UpdatePolicy;
  getIntegerInputValue: (path: string, value: number) => string;
  updateIntegerInput: (
    path: string,
    rawValue: string,
    minValue: number,
    applyValue: (value: number) => void,
  ) => void;
  finishIntegerInput: (path: string, fallbackValue: number) => void;
};

function RuleSummaryCard({
  title,
  summary,
  active,
}: {
  title: string;
  summary: string;
  active: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className='rounded-lg border border-border bg-white px-3 py-2.5 shadow-sm'>
      <div className='flex items-start justify-between gap-3'>
        <div className='min-w-0'>
          <h3 className='text-sm font-medium leading-5 text-foreground'>
            {title}
          </h3>
          <p className='mt-1 text-xs leading-5 text-muted-foreground'>
            {summary}
          </p>
        </div>
        <Badge
          variant='secondary'
          className={cn(
            'mt-0.5 shrink-0 gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium',
            active
              ? 'bg-emerald-50 text-emerald-700'
              : 'bg-muted text-muted-foreground',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              active ? 'bg-emerald-500' : 'bg-muted-foreground/50',
            )}
          />
          {t(
            active
              ? 'module.operationsCreditNotifications.config.deliveryRules.active'
              : 'module.operationsCreditNotifications.config.deliveryRules.inactive',
          )}
        </Badge>
      </div>
    </div>
  );
}

export function CreditNotificationDeliveryRulesSection({
  contactMode,
  policy,
  updatePolicy,
  getIntegerInputValue,
  updateIntegerInput,
  finishIntegerInput,
}: CreditNotificationDeliveryRulesSectionProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const yes = t(
    'module.operationsCreditNotifications.config.deliveryRules.yes',
  );
  const no = t('module.operationsCreditNotifications.config.deliveryRules.no');
  const summaries = useMemo(() => {
    const items = [
      {
        key: 'frequency',
        title: t(
          'module.operationsCreditNotifications.config.sections.frequency',
        ),
        active:
          policy.frequency.per_mobile_per_day > 0 ||
          policy.frequency.per_creator_per_type_per_day > 0,
        summary:
          contactMode === 'email'
            ? t(
                'module.operationsCreditNotifications.config.deliveryRules.summaries.frequencyEmail',
                {
                  perRecipient: policy.frequency.per_mobile_per_day,
                  perCreatorType: policy.frequency.per_creator_per_type_per_day,
                },
              )
            : t(
                'module.operationsCreditNotifications.config.deliveryRules.summaries.frequency',
                {
                  perMobile: policy.frequency.per_mobile_per_day,
                  perCreatorType: policy.frequency.per_creator_per_type_per_day,
                },
              ),
      },
      {
        key: 'quietHours',
        title: t(
          'module.operationsCreditNotifications.config.sections.quietHours',
        ),
        active: policy.quiet_hours.enabled,
        summary: policy.quiet_hours.enabled
          ? t(
              'module.operationsCreditNotifications.config.deliveryRules.summaries.quietHoursOn',
              {
                start: policy.quiet_hours.start,
                end: policy.quiet_hours.end,
                timezone: policy.quiet_hours.timezone || 'Asia/Shanghai',
              },
            )
          : t(
              'module.operationsCreditNotifications.config.deliveryRules.summaries.quietHoursOff',
            ),
      },
      {
        key: 'softlimit',
        title: t(
          'module.operationsCreditNotifications.config.sections.softlimit',
        ),
        active: policy.softlimit.enabled,
        summary:
          contactMode === 'email'
            ? t(
                'module.operationsCreditNotifications.config.deliveryRules.summaries.softlimitEmail',
                {
                  threshold: policy.softlimit.threshold.value,
                  teacherAlert: policy.softlimit.teacher_page_alert ? yes : no,
                  debugLock: policy.softlimit.disable_debug ? yes : no,
                },
              )
            : t(
                'module.operationsCreditNotifications.config.deliveryRules.summaries.softlimit',
                {
                  threshold: policy.softlimit.threshold.value,
                  teacherAlert: policy.softlimit.teacher_page_alert ? yes : no,
                  debugLock: policy.softlimit.disable_debug ? yes : no,
                  sms: policy.softlimit.sms_enabled ? yes : no,
                },
              ),
      },
    ];

    if (contactMode === 'phone') {
      items.splice(2, 0, {
        key: 'budget',
        title: t('module.operationsCreditNotifications.config.sections.budget'),
        active:
          policy.budget.daily_sms_limit > 0 || policy.budget.dry_run_required,
        summary: t(
          'module.operationsCreditNotifications.config.deliveryRules.summaries.budget',
          {
            limit: policy.budget.daily_sms_limit,
            cost: policy.budget.sms_unit_cost,
            dryRun: policy.budget.dry_run_required ? yes : no,
          },
        ),
      });
    }

    return items;
  }, [contactMode, no, policy, t, yes]);

  return (
    <>
      <ConfigSection
        title={t(
          'module.operationsCreditNotifications.config.sections.deliveryPolicy',
        )}
        description={t(
          contactMode === 'email'
            ? 'module.operationsCreditNotifications.config.deliveryRules.descriptionEmail'
            : 'module.operationsCreditNotifications.config.deliveryRules.description',
        )}
        action={
          <Button
            type='button'
            variant='outline'
            onClick={() => setEditing(true)}
          >
            {t(
              'module.operationsCreditNotifications.config.deliveryRules.edit',
            )}
          </Button>
        }
      >
        <div className='grid gap-3 lg:grid-cols-2'>
          {summaries.map(item => (
            <RuleSummaryCard
              key={item.key}
              title={item.title}
              summary={item.summary}
              active={item.active}
            />
          ))}
        </div>
      </ConfigSection>

      <Dialog
        open={editing}
        onOpenChange={setEditing}
      >
        <DialogContent className='max-h-[calc(100vh-48px)] max-w-5xl overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>
              {t(
                'module.operationsCreditNotifications.config.deliveryRules.dialogTitle',
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                contactMode === 'email'
                  ? 'module.operationsCreditNotifications.config.deliveryRules.dialogDescriptionEmail'
                  : 'module.operationsCreditNotifications.config.deliveryRules.dialogDescription',
              )}
            </DialogDescription>
          </DialogHeader>
          <div className='grid gap-4 xl:grid-cols-2'>
            <FrequencyCard
              contactMode={contactMode}
              policy={policy}
              updatePolicy={updatePolicy}
              getIntegerInputValue={getIntegerInputValue}
              updateIntegerInput={updateIntegerInput}
              finishIntegerInput={finishIntegerInput}
            />
            <QuietHoursCard
              policy={policy}
              updatePolicy={updatePolicy}
            />
            {contactMode === 'phone' ? (
              <BudgetCard
                contactMode={contactMode}
                policy={policy}
                updatePolicy={updatePolicy}
                getIntegerInputValue={getIntegerInputValue}
                updateIntegerInput={updateIntegerInput}
                finishIntegerInput={finishIntegerInput}
              />
            ) : null}
            <SoftlimitCard
              contactMode={contactMode}
              policy={policy}
              updatePolicy={updatePolicy}
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
