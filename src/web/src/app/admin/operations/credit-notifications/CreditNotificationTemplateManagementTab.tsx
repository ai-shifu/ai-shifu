import { ChevronDown, ChevronUp, Plus, RefreshCw, Search } from 'lucide-react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import { useEnvStore } from '@/c-store';
import type { EnvStoreState } from '@/c-types/store';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Textarea } from '@/components/ui/Textarea';
import { toast } from '@/hooks/useToast';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { resolveContactMode } from '@/lib/resolve-contact-mode';
import type {
  CreditNotificationType,
  AdminOperationCreditNotificationPolicy,
  AdminOperationCreditNotificationTemplateOption,
} from '../operation-credit-notification-types';
import { CreditNotificationConfigOverviewTable } from './CreditNotificationConfigOverviewTable';

type TemplateColumn = {
  key: string;
  header: React.ReactNode;
  className?: string;
  stickyRight?: boolean;
};

type TemplateBindingStatus = 'loading' | 'ready' | 'unavailable';

const TEMPLATE_STATUS_KEYS: Record<string, string> = {
  AUDIT_SATE_CANCEL:
    'module.operationsCreditNotifications.templateManagement.status.AUDIT_SATE_CANCEL',
  AUDIT_STATE_CANCEL:
    'module.operationsCreditNotifications.templateManagement.status.AUDIT_STATE_CANCEL',
  AUDIT_STATE_INIT:
    'module.operationsCreditNotifications.templateManagement.status.AUDIT_STATE_INIT',
  AUDIT_STATE_NOT_PASS:
    'module.operationsCreditNotifications.templateManagement.status.AUDIT_STATE_NOT_PASS',
  AUDIT_STATE_PASS:
    'module.operationsCreditNotifications.templateManagement.status.AUDIT_STATE_PASS',
};

const TEMPLATE_TYPE_KEYS: Record<string, string> = {
  '0': 'module.operationsCreditNotifications.templateManagement.type.0',
  '1': 'module.operationsCreditNotifications.templateManagement.type.1',
  '2': 'module.operationsCreditNotifications.templateManagement.type.2',
  '6': 'module.operationsCreditNotifications.templateManagement.type.6',
};

const EMAIL_TEMPLATE_VARIABLES = [
  {
    token: '${product}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.product',
  },
  {
    token: '${window}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.window',
  },
  {
    token: '${credits}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.credits',
  },
  {
    token: '${expires_at}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.expiresAt',
  },
  {
    token: '${available_credits}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.availableCredits',
  },
  {
    token: '${estimated_remaining_days}',
    labelKey:
      'module.operationsCreditNotifications.templateManagement.emailVariables.estimatedRemainingDays',
  },
];

const EMAIL_TEMPLATE_NOTIFICATION_TYPES: Array<{
  value: CreditNotificationType;
  labelKey: string;
}> = [
  {
    value: 'credit_granted',
    labelKey: 'module.operationsCreditNotifications.type.credit_granted',
  },
  {
    value: 'credit_expiring',
    labelKey: 'module.operationsCreditNotifications.type.credit_expiring',
  },
  {
    value: 'low_balance',
    labelKey: 'module.operationsCreditNotifications.type.low_balance',
  },
];

export function CreditNotificationTemplateManagementTab({
  templates,
  active,
  loading,
  error,
  policy,
  bindingStatus,
  refresh,
  onViewed,
  onFilterApplied,
  onDetailOpened,
  saveEmailTemplate,
  updateEmailTemplateStatus,
}: {
  templates: AdminOperationCreditNotificationTemplateOption[];
  active: boolean;
  loading: boolean;
  error: string;
  policy: AdminOperationCreditNotificationPolicy;
  bindingStatus: TemplateBindingStatus;
  refresh: () => Promise<void>;
  onViewed: () => void;
  onFilterApplied: (filter: 'keyword' | 'status') => void;
  onDetailOpened: () => void;
  saveEmailTemplate: (
    payload: Record<string, unknown>,
    notificationTemplateBid?: string,
  ) => Promise<void>;
  updateEmailTemplateStatus: (
    notificationTemplateBid: string,
    templateStatus: 'active' | 'disabled',
  ) => Promise<void>;
}) {
  const { t } = useTranslation();
  const loginMethodsEnabled = useEnvStore(
    (state: EnvStoreState) => state.loginMethodsEnabled,
  );
  const defaultLoginMethod = useEnvStore(
    (state: EnvStoreState) => state.defaultLoginMethod,
  );
  const contactMode = resolveContactMode(
    loginMethodsEnabled,
    defaultLoginMethod,
  );
  const [keyword, setKeyword] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [selectedTemplate, setSelectedTemplate] =
    React.useState<AdminOperationCreditNotificationTemplateOption | null>(null);
  const [editingTemplate, setEditingTemplate] =
    React.useState<AdminOperationCreditNotificationTemplateOption | null>(null);
  const [emailTemplateStatus, setEmailTemplateStatus] = React.useState('draft');
  const [emailTemplateNotificationTypes, setEmailTemplateNotificationTypes] =
    React.useState<CreditNotificationType[]>([]);
  const [savingEmailTemplate, setSavingEmailTemplate] = React.useState(false);
  const [emailVariablesExpanded, setEmailVariablesExpanded] =
    React.useState(true);
  const activeEmailFieldRef = React.useRef<
    HTMLInputElement | HTMLTextAreaElement | null
  >(null);
  const hasTrackedViewRef = React.useRef(false);

  React.useEffect(() => {
    if (!active || hasTrackedViewRef.current) {
      return;
    }
    hasTrackedViewRef.current = true;
    onViewed();
  }, [active, contactMode, onViewed]);

  const statusLabel = React.useCallback(
    (value: string) => {
      if (contactMode === 'email') {
        return t(
          `module.operationsCreditNotifications.templateManagement.emailStatus.${value}`,
        );
      }
      return TEMPLATE_STATUS_KEYS[value]
        ? t(TEMPLATE_STATUS_KEYS[value])
        : value || '--';
    },
    [contactMode, t],
  );
  const typeLabel = React.useCallback(
    (value: string) =>
      TEMPLATE_TYPE_KEYS[value] ? t(TEMPLATE_TYPE_KEYS[value]) : value || '--',
    [t],
  );
  const openEmailTemplate = React.useCallback(
    (template: AdminOperationCreditNotificationTemplateOption) => {
      setEditingTemplate(template);
      setEmailTemplateStatus(template.template_status || 'draft');
      setEmailTemplateNotificationTypes(
        template.compatible_notification_types || [],
      );
      setEmailVariablesExpanded(true);
    },
    [],
  );
  const bindingsFor = React.useCallback(
    (templateCode: string) => {
      if (policy.rules.length) {
        return policy.rules
          .filter(rule => rule.template_code === templateCode)
          .map(rule => ({
            key: rule.rule_bid,
            label: rule.legacy
              ? t(
                  `module.operationsCreditNotifications.type.${rule.trigger_event}`,
                )
              : rule.name || '--',
          }));
      }
      return Object.entries(policy.types)
        .filter(([, config]) => config.template_code === templateCode)
        .map(([notificationType]) => ({
          key: notificationType,
          label: t(
            `module.operationsCreditNotifications.type.${notificationType}`,
          ),
        }));
    },
    [policy.rules, policy.types, t],
  );

  const statuses = React.useMemo(
    () =>
      Array.from(
        new Set(templates.map(item => item.template_status).filter(Boolean)),
      ).sort(),
    [templates],
  );
  const rows = React.useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return templates
      .filter(item => !status || item.template_status === status)
      .filter(item => {
        if (!normalizedKeyword) return true;
        return [item.template_name, item.template_code, item.template_content]
          .join(' ')
          .toLowerCase()
          .includes(normalizedKeyword);
      })
      .map(item => ({ ...item, key: item.template_code }));
  }, [keyword, status, templates]);

  const columns: TemplateColumn[] = [
    {
      key: 'name',
      header: t(
        'module.operationsCreditNotifications.templateManagement.columns.name',
      ),
      className: 'w-56 min-w-56',
    },
    {
      key: 'status',
      header:
        contactMode === 'email'
          ? t(
              'module.operationsCreditNotifications.templateManagement.emailFields.status',
            )
          : t(
              'module.operationsCreditNotifications.templateManagement.columns.status',
            ),
      className: 'w-28 min-w-28 whitespace-nowrap',
    },
    {
      key: 'type',
      header: t(
        'module.operationsCreditNotifications.templateManagement.columns.type',
      ),
      className: 'w-24 min-w-24 whitespace-nowrap',
    },
    {
      key: 'bindings',
      header: t(
        'module.operationsCreditNotifications.templateManagement.columns.bindings',
      ),
      className: 'w-28 min-w-28',
    },
    {
      key: 'content',
      header: t(
        'module.operationsCreditNotifications.templateManagement.columns.content',
      ),
      className: 'w-[28rem] min-w-[28rem] max-w-[28rem]',
    },
    {
      key: 'action',
      header: t(
        'module.operationsCreditNotifications.templateManagement.columns.action',
      ),
      className: 'w-24 min-w-24 whitespace-nowrap text-center',
      stickyRight: true,
    },
  ];
  const templateTitle =
    contactMode === 'email'
      ? t('module.operationsCreditNotifications.templateManagement.emailTitle')
      : t('module.operationsCreditNotifications.templateManagement.smsTitle');
  const templateDescription =
    contactMode === 'email'
      ? t(
          'module.operationsCreditNotifications.templateManagement.emailDescription',
        )
      : t(
          'module.operationsCreditNotifications.templateManagement.smsDescription',
        );
  const refreshLabel =
    contactMode === 'email'
      ? t('module.operationsCreditNotifications.templateManagement.reload')
      : t('module.operationsCreditNotifications.templateManagement.refresh');
  const smsLoadError = t(
    'module.operationsCreditNotifications.templateManagement.loadError',
  );
  const emailLoadError = t(
    'module.operationsCreditNotifications.templateManagement.emailLoadError',
  );
  const emailVariablesToggleLabel = emailVariablesExpanded
    ? t(
        'module.operationsCreditNotifications.templateManagement.emailVariables.collapse',
      )
    : t(
        'module.operationsCreditNotifications.templateManagement.emailVariables.expand',
      );
  return (
    <div className='space-y-4 pb-6'>
      <div className='flex flex-wrap items-end justify-between gap-3'>
        <div>
          <h2 className='text-base font-semibold'>{templateTitle}</h2>
          <p className='mt-1 text-sm text-muted-foreground'>
            {templateDescription}
          </p>
        </div>
        <div className='flex gap-2'>
          <Button
            type='button'
            variant='outline'
            onClick={() => void refresh()}
            disabled={loading}
          >
            {contactMode !== 'email' ? (
              <RefreshCw
                className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`}
              />
            ) : null}
            {refreshLabel}
          </Button>
          {contactMode === 'email' ? (
            <Button
              type='button'
              onClick={() =>
                openEmailTemplate({
                  channel: 'email',
                  provider: 'smtp',
                  template_code: '',
                  template_name: '',
                  template_content: '',
                  email_subject: '',
                  email_html_body: '',
                  locale: 'en-US',
                  template_status: 'draft',
                  template_type: 'email',
                  sync_status: 'local',
                  error_code: '',
                  error_message: '',
                  last_synced_at: '',
                  source: 'local',
                })
              }
            >
              <Plus className='mr-2 h-4 w-4' />
              {t(
                'module.operationsCreditNotifications.templateManagement.create',
              )}
            </Button>
          ) : null}
        </div>
      </div>
      <div className='flex flex-wrap gap-3'>
        <div className='relative min-w-64 flex-1'>
          <Search className='absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground' />
          <Input
            value={keyword}
            onChange={event => setKeyword(event.target.value)}
            onBlur={() => {
              if (keyword.trim()) {
                onFilterApplied('keyword');
              }
            }}
            className='pl-9'
            placeholder={t(
              'module.operationsCreditNotifications.templateManagement.searchPlaceholder',
            )}
          />
        </div>
        <Select
          value={status || '__all__'}
          onValueChange={value => {
            setStatus(value === '__all__' ? '' : value);
            if (value !== '__all__') {
              onFilterApplied('status');
            }
          }}
        >
          <SelectTrigger
            className='h-10 min-w-48 bg-white'
            aria-label={
              contactMode === 'email'
                ? t(
                    'module.operationsCreditNotifications.templateManagement.emailStatusFilter',
                  )
                : t(
                    'module.operationsCreditNotifications.templateManagement.statusFilter',
                  )
            }
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value='__all__'>
              {contactMode === 'email'
                ? t(
                    'module.operationsCreditNotifications.templateManagement.allEmailStatuses',
                  )
                : t(
                    'module.operationsCreditNotifications.templateManagement.allStatuses',
                  )}
            </SelectItem>
            {statuses.map(value => (
              <SelectItem
                key={value}
                value={value}
              >
                {statusLabel(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error ? (
        <p className='text-sm text-destructive'>
          {contactMode === 'email' ? emailLoadError : smsLoadError}
        </p>
      ) : null}
      {rows.length ? (
        <TooltipProvider delayDuration={150}>
          <CreditNotificationConfigOverviewTable
            columns={columns}
            rows={rows}
            renderCell={(row, column) => {
              if (column.key === 'name')
                return (
                  <div>
                    <div className='font-medium'>
                      {row.template_name || '--'}
                    </div>
                    <code className='text-xs text-muted-foreground'>
                      {row.template_code}
                    </code>
                  </div>
                );
              if (column.key === 'status')
                return (
                  <Badge
                    variant='secondary'
                    className='whitespace-nowrap'
                  >
                    {statusLabel(row.template_status)}
                  </Badge>
                );
              if (column.key === 'type')
                return (
                  <span className='text-sm'>
                    {typeLabel(row.template_type)}
                  </span>
                );
              if (column.key === 'bindings') {
                if (bindingStatus === 'loading') {
                  return (
                    <span className='text-sm text-muted-foreground'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.bindingsLoading',
                      )}
                    </span>
                  );
                }
                if (bindingStatus === 'unavailable') {
                  return (
                    <span className='text-sm text-muted-foreground'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.bindingsUnavailable',
                      )}
                    </span>
                  );
                }
                const bindings = bindingsFor(row.template_code);
                return bindings.length ? (
                  <div className='flex flex-wrap gap-x-2 gap-y-1 text-sm text-muted-foreground'>
                    {bindings.map(binding => (
                      <span key={binding.key}>{binding.label}</span>
                    ))}
                  </div>
                ) : (
                  <span className='text-sm text-muted-foreground'>
                    {t(
                      'module.operationsCreditNotifications.templateManagement.unbound',
                    )}
                  </span>
                );
              }
              if (column.key === 'content')
                return (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className='line-clamp-2 break-words text-sm leading-5'>
                        {row.template_content || '--'}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className='max-w-[32rem] whitespace-pre-wrap break-words text-left leading-5'>
                      {row.template_content || '--'}
                    </TooltipContent>
                  </Tooltip>
                );
              return (
                <div className='flex justify-center'>
                  <AdminRowActions
                    label={t(
                      'module.operationsCreditNotifications.actions.more',
                    )}
                    className='whitespace-nowrap'
                    actions={[
                      {
                        key: 'detail',
                        label: t(
                          'module.operationsCreditNotifications.actions.detail',
                        ),
                        onClick: () => {
                          setSelectedTemplate(row);
                          onDetailOpened();
                        },
                      },
                      ...(contactMode === 'email'
                        ? [
                            {
                              key: 'toggle-status',
                              label:
                                row.template_status === 'active'
                                  ? t(
                                      'module.operationsCreditNotifications.actions.disable',
                                    )
                                  : t(
                                      'module.operationsCreditNotifications.actions.enable',
                                    ),
                              onClick: () => {
                                const notificationTemplateBid =
                                  row.notification_template_bid;
                                if (!notificationTemplateBid) return;
                                void updateEmailTemplateStatus(
                                  notificationTemplateBid,
                                  row.template_status === 'active'
                                    ? 'disabled'
                                    : 'active',
                                );
                              },
                            },
                            {
                              key: 'edit',
                              label: t(
                                'module.operationsCreditNotifications.ruleManagement.edit',
                              ),
                              onClick: () => openEmailTemplate(row),
                            },
                          ]
                        : []),
                    ]}
                  />
                </div>
              );
            }}
          />
        </TooltipProvider>
      ) : (
        <div className='rounded-lg border border-dashed border-border px-6 py-12 text-center text-sm text-muted-foreground'>
          {loading
            ? t(
                'module.operationsCreditNotifications.templateManagement.loading',
              )
            : t(
                'module.operationsCreditNotifications.templateManagement.empty',
              )}
        </div>
      )}
      <Sheet
        open={Boolean(selectedTemplate)}
        onOpenChange={open => {
          if (!open) setSelectedTemplate(null);
        }}
      >
        <SheetContent className='flex w-full flex-col overflow-hidden border-border bg-white p-0 sm:w-[420px] md:w-[560px]'>
          <SheetHeader className='border-b border-border px-6 py-4 pe-12'>
            <SheetTitle>{selectedTemplate?.template_name || '--'}</SheetTitle>
            <SheetDescription>
              {t(
                'module.operationsCreditNotifications.templateManagement.detailDescription',
              )}
            </SheetDescription>
          </SheetHeader>
          {selectedTemplate ? (
            <div className='flex-1 space-y-5 overflow-auto px-6 py-5 text-sm'>
              {[
                {
                  label: t(
                    'module.operationsCreditNotifications.templateManagement.detail.code',
                  ),
                  value: selectedTemplate.template_code,
                },
                {
                  label: t(
                    'module.operationsCreditNotifications.templateManagement.detail.status',
                  ),
                  value: statusLabel(selectedTemplate.template_status),
                },
                {
                  label: t(
                    'module.operationsCreditNotifications.templateManagement.detail.type',
                  ),
                  value: typeLabel(selectedTemplate.template_type),
                },
                {
                  label: t(
                    'module.operationsCreditNotifications.templateManagement.detail.syncedAt',
                  ),
                  value:
                    formatAdminUtcDateTime(selectedTemplate.last_synced_at) ||
                    '--',
                },
              ].map(item => (
                <div
                  key={item.label}
                  className='grid grid-cols-[120px_1fr] gap-4'
                >
                  <span className='text-muted-foreground'>{item.label}</span>
                  <span className='break-all text-right'>{item.value}</span>
                </div>
              ))}
              <div>
                <div className='mb-2 text-muted-foreground'>
                  {t(
                    'module.operationsCreditNotifications.templateManagement.detail.content',
                  )}
                </div>
                <div className='whitespace-pre-wrap rounded-md bg-muted/40 p-3 leading-6'>
                  {selectedTemplate.template_content || '--'}
                </div>
              </div>
              <div>
                <div className='mb-2 text-muted-foreground'>
                  {t(
                    'module.operationsCreditNotifications.templateManagement.detail.variables',
                  )}
                </div>
                <div className='flex flex-wrap gap-1'>
                  {selectedTemplate.placeholders?.length
                    ? selectedTemplate.placeholders.map(value => (
                        <code
                          key={value}
                          className='rounded bg-muted px-2 py-1 text-xs'
                        >
                          {value}
                        </code>
                      ))
                    : '--'}
                </div>
              </div>
              {selectedTemplate.error_message ? (
                <div>
                  <div className='mb-2 text-muted-foreground'>
                    {t(
                      'module.operationsCreditNotifications.templateManagement.detail.error',
                    )}
                  </div>
                  <div className='rounded-md border border-destructive/30 bg-destructive/5 p-3 text-destructive'>
                    {selectedTemplate.error_message}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
      <Dialog
        open={Boolean(editingTemplate)}
        onOpenChange={open => {
          if (!open && !savingEmailTemplate) setEditingTemplate(null);
        }}
      >
        <DialogContent className='flex max-h-[calc(100vh-48px)] max-w-3xl flex-col overflow-hidden'>
          <DialogHeader>
            <DialogTitle>
              {t(
                'module.operationsCreditNotifications.templateManagement.emailTitle',
              )}
            </DialogTitle>
            <DialogDescription>
              {t(
                'module.operationsCreditNotifications.templateManagement.emailDescription',
              )}
            </DialogDescription>
          </DialogHeader>
          {editingTemplate ? (
            <form
              className='mt-2 flex min-h-0 flex-1 flex-col'
              onSubmit={event => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                const payload = Object.fromEntries(form.entries()) as Record<
                  string,
                  unknown
                >;
                payload.template_status = emailTemplateStatus;
                payload.locale = 'en-US';
                payload.applicable_notification_types =
                  emailTemplateNotificationTypes;
                setSavingEmailTemplate(true);
                void saveEmailTemplate(
                  payload,
                  editingTemplate.notification_template_bid,
                )
                  .then(() => setEditingTemplate(null))
                  .catch(() => {
                    toast({
                      title: t(
                        'module.operationsCreditNotifications.templateManagement.emailSaveError',
                      ),
                      variant: 'destructive',
                    });
                  })
                  .finally(() => setSavingEmailTemplate(false));
              }}
            >
              <div className='space-y-4 overflow-y-auto pe-1'>
                <div className='grid gap-x-4 gap-y-5 sm:grid-cols-2'>
                  <div className='space-y-2'>
                    <Label htmlFor='email-template-template-name'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.emailFields.name',
                      )}
                    </Label>
                    <Input
                      id='email-template-template-name'
                      name='template_name'
                      className='h-10'
                      defaultValue={editingTemplate.template_name || ''}
                      onFocus={event => {
                        activeEmailFieldRef.current = event.currentTarget;
                      }}
                      required
                    />
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='email-template-locale'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.emailFields.locale',
                      )}
                    </Label>
                    <Input
                      id='email-template-locale'
                      className='h-10 bg-muted'
                      value={t(
                        'module.operationsCreditNotifications.templateManagement.emailLocales.enUS',
                      )}
                      disabled
                    />
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='email-template-status'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.emailFields.status',
                      )}
                    </Label>
                    <Select
                      value={emailTemplateStatus}
                      onValueChange={setEmailTemplateStatus}
                    >
                      <SelectTrigger
                        id='email-template-status'
                        className='bg-white'
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value='draft'>
                          {t(
                            'module.operationsCreditNotifications.templateManagement.emailStatus.draft',
                          )}
                        </SelectItem>
                        <SelectItem value='active'>
                          {t(
                            'module.operationsCreditNotifications.templateManagement.emailStatus.active',
                          )}
                        </SelectItem>
                        <SelectItem value='disabled'>
                          {t(
                            'module.operationsCreditNotifications.templateManagement.emailStatus.disabled',
                          )}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className='space-y-2'>
                    <Label htmlFor='email-template-subject'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.emailFields.subject',
                      )}
                    </Label>
                    <Input
                      id='email-template-subject'
                      name='email_subject'
                      className='h-10'
                      defaultValue={editingTemplate.email_subject || ''}
                      onFocus={event => {
                        activeEmailFieldRef.current = event.currentTarget;
                      }}
                      required
                    />
                  </div>
                </div>
                <div className='rounded-md border border-border bg-muted/30 p-3'>
                  <p className='text-sm font-medium text-foreground'>
                    {t(
                      'module.operationsCreditNotifications.templateManagement.emailFields.notificationTypes',
                    )}
                  </p>
                  <p className='mt-1 text-xs leading-5 text-muted-foreground'>
                    {t(
                      'module.operationsCreditNotifications.templateManagement.emailFields.notificationTypesHint',
                    )}
                  </p>
                  <div className='mt-3 grid gap-2 sm:grid-cols-3'>
                    {EMAIL_TEMPLATE_NOTIFICATION_TYPES.map(option => {
                      const checked = emailTemplateNotificationTypes.includes(
                        option.value,
                      );
                      return (
                        <label
                          key={option.value}
                          className='flex cursor-pointer items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm'
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={value => {
                              setEmailTemplateNotificationTypes(current =>
                                value
                                  ? [...new Set([...current, option.value])]
                                  : current.filter(
                                      notificationType =>
                                        notificationType !== option.value,
                                    ),
                              );
                            }}
                          />
                          {t(option.labelKey)}
                        </label>
                      );
                    })}
                  </div>
                </div>
                <div className='rounded-md border border-border bg-muted/30 p-3'>
                  <div className='flex items-center justify-between gap-3'>
                    <p className='text-sm font-medium'>
                      {t(
                        'module.operationsCreditNotifications.templateManagement.detail.variables',
                      )}
                    </p>
                    <TooltipProvider delayDuration={150}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type='button'
                            variant='ghost'
                            size='icon'
                            className='h-7 w-7'
                            aria-expanded={emailVariablesExpanded}
                            aria-label={emailVariablesToggleLabel}
                            onClick={() =>
                              setEmailVariablesExpanded(expanded => !expanded)
                            }
                          >
                            {emailVariablesExpanded ? (
                              <ChevronUp className='h-4 w-4' />
                            ) : (
                              <ChevronDown className='h-4 w-4' />
                            )}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {emailVariablesToggleLabel}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                  {emailVariablesExpanded ? (
                    <div className='mt-2 flex flex-wrap gap-2'>
                      {EMAIL_TEMPLATE_VARIABLES.map(variable => (
                        <Button
                          key={variable.token}
                          type='button'
                          variant='outline'
                          size='sm'
                          onClick={() => {
                            const field = activeEmailFieldRef.current;
                            if (!field) return;
                            const start =
                              field.selectionStart ?? field.value.length;
                            const end = field.selectionEnd ?? start;
                            field.value =
                              field.value.slice(0, start) +
                              variable.token +
                              field.value.slice(end);
                            field.focus();
                            field.setSelectionRange(
                              start + variable.token.length,
                              start + variable.token.length,
                            );
                          }}
                        >
                          <span>{variable.token}</span>
                          <span className='ms-1 text-muted-foreground'>
                            {t(variable.labelKey)}
                          </span>
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className='space-y-2'>
                  <Label htmlFor='email-template-body'>
                    {t(
                      'module.operationsCreditNotifications.templateManagement.emailFields.htmlBody',
                    )}
                  </Label>
                  <Textarea
                    id='email-template-body'
                    name='email_html_body'
                    defaultValue={
                      editingTemplate.email_html_body ||
                      editingTemplate.template_content ||
                      ''
                    }
                    onFocus={event => {
                      activeEmailFieldRef.current = event.currentTarget;
                    }}
                    required
                    rows={8}
                  />
                </div>
              </div>
              <DialogFooter className='mt-4 border-t border-border pt-4'>
                <Button
                  type='submit'
                  disabled={savingEmailTemplate}
                >
                  {t('common.core.save')}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
