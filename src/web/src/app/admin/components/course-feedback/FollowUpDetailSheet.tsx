'use client';

import type { LoginIdentifierType } from '@/lib/login-identifiers';

import {
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';
import ErrorDisplay from '@/components/ErrorDisplay';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { formatAdminUtcDateTime } from '@/app/admin/lib/date-time';
import { cn } from '@/lib/utils';
import {
  formatDisplayValue,
  resolvePrimaryAccount,
  type CourseFeedbackErrorState,
} from './course-feedback-display';

/**
 * Structural subset of the follow-up detail payload rendered by the sheet.
 * Both the dashboard and the operator admin responses satisfy it.
 */
export type FollowUpDetailSheetData = {
  basic_info?: {
    user_bid?: string;
    mobile?: string;
    email?: string;
    nickname?: string;
    chapter_title?: string;
    lesson_title?: string;
    created_at?: string;
    turn_index?: number | null;
  };
  current_record?: {
    follow_up_content?: string;
    answer_content?: string;
    source_output_content?: string;
  };
  timeline?: Array<{
    role: string;
    content?: string;
    created_at?: string;
    is_current?: boolean;
  }>;
};

/**
 * Already-translated labels. Each surface resolves them from its own i18n
 * namespace so translation keys stay with the page that owns them.
 */
export type FollowUpDetailSheetLabels = {
  title: string;
  basicInfoSection: string;
  currentRecordSection: string;
  currentRecordHint: string;
  timelineSection: string;
  user: string;
  nickname: string;
  /** Renders the user id row when provided. */
  userId?: string;
  followUpTime: string;
  turnIndex: string;
  turnIndexHelp: string;
  /**
   * Renders the source output block when provided, using `unavailable`
   * as its highlighted empty state.
   */
  sourceOutput?: {
    title: string;
    unavailable: string;
  };
  currentFollowUp: string;
  currentAnswer: string;
  timelineCurrent: string;
};

type FollowUpDetailSheetProps = {
  open: boolean;
  detail: FollowUpDetailSheetData | null;
  loading: boolean;
  error: CourseFeedbackErrorState | null;
  emptyValue: string;
  displayIdentifierType: LoginIdentifierType;
  defaultUserName: string;
  labels: FollowUpDetailSheetLabels;
  resolveLessonDisplay: (values: {
    lessonTitle?: string;
    chapterTitle?: string;
    emptyValue: string;
  }) => string;
  resolveOutlineFieldLabel: (values: {
    lessonTitle?: string;
    chapterTitle?: string;
  }) => string;
  formatTurnIndex: (turnIndex: number | null | undefined) => string;
  resolveRoleLabel: (role: string) => string;
  onRetry: () => void;
  onOpenChange: (open: boolean) => void;
};

const DetailRow = ({ label, value }: { label: string; value: string }) => (
  <div className='flex items-start justify-between gap-4 text-sm'>
    <span className='text-muted-foreground'>{label}</span>
    <span className='max-w-[65%] break-words text-right text-foreground'>
      {value}
    </span>
  </div>
);

const Section = ({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) => (
  <section className='space-y-3 rounded-lg border border-border bg-white p-4'>
    <div className='space-y-1'>
      <h4 className='text-sm font-semibold text-foreground'>{title}</h4>
      {description ? (
        <p className='text-xs leading-5 text-muted-foreground'>{description}</p>
      ) : null}
    </div>
    <div className='space-y-3'>{children}</div>
  </section>
);

const COLLAPSED_TEXT_STYLE: CSSProperties = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: 4,
  overflow: 'hidden',
};

const ExpandableTextBlock = ({
  title,
  content,
  emptyValue,
  emptyState,
  variant = 'card',
  emphasizeEmptyState = false,
}: {
  title?: string;
  content?: string;
  emptyValue: string;
  emptyState?: string;
  variant?: 'card' | 'plain';
  emphasizeEmptyState?: boolean;
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const normalizedContent = content?.trim() || '';
  const resolvedContent = normalizedContent || emptyState || emptyValue;
  const canToggle = normalizedContent.length > 80;
  const showEmptyStateStyle = emphasizeEmptyState && !normalizedContent;

  useEffect(() => {
    setExpanded(false);
  }, [resolvedContent]);

  return (
    <div className='space-y-2'>
      {title ? (
        <div className='text-sm font-medium text-foreground'>{title}</div>
      ) : null}
      <div
        className={cn(
          'px-4 py-3',
          variant === 'card'
            ? showEmptyStateStyle
              ? 'rounded-xl border border-dashed border-amber-200 bg-amber-50/70'
              : 'rounded-xl border border-border bg-muted/[0.16]'
            : 'rounded-lg bg-muted/[0.12]',
        )}
      >
        <div
          className={cn(
            'break-words whitespace-pre-wrap text-sm leading-6',
            showEmptyStateStyle ? 'text-amber-800/90' : 'text-foreground',
          )}
          style={expanded || !canToggle ? undefined : COLLAPSED_TEXT_STYLE}
        >
          {resolvedContent}
        </div>
        {canToggle ? (
          <div className='mt-2 flex justify-end'>
            <button
              type='button'
              className='text-sm font-medium text-primary transition-colors hover:text-primary/80'
              onClick={() => setExpanded(previous => !previous)}
            >
              {expanded ? t('common.core.collapse') : t('common.core.expand')}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default function FollowUpDetailSheet({
  open,
  detail,
  loading,
  error,
  emptyValue,
  displayIdentifierType,
  defaultUserName,
  labels,
  resolveLessonDisplay,
  resolveOutlineFieldLabel,
  formatTurnIndex,
  resolveRoleLabel,
  onRetry,
  onOpenChange,
}: FollowUpDetailSheetProps) {
  const basicInfo = detail?.basic_info;
  const currentRecord = detail?.current_record;
  const timeline = detail?.timeline || [];

  const primaryAccount = useMemo(
    () =>
      resolvePrimaryAccount({
        mobile: basicInfo?.mobile,
        email: basicInfo?.email,
        userBid: basicInfo?.user_bid,
        displayIdentifierType,
        emptyValue,
      }),
    [
      basicInfo?.email,
      basicInfo?.mobile,
      basicInfo?.user_bid,
      displayIdentifierType,
      emptyValue,
    ],
  );
  const nickname = useMemo(() => {
    const normalizedNickname = basicInfo?.nickname?.trim() || '';
    return normalizedNickname || defaultUserName;
  }, [basicInfo?.nickname, defaultUserName]);
  const turnIndexLabel = useMemo(
    () => formatTurnIndex(basicInfo?.turn_index),
    [basicInfo?.turn_index, formatTurnIndex],
  );

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-border bg-white p-0 sm:w-[420px] md:w-[520px] lg:w-[640px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pe-12'>
          <SheetTitle className='text-base font-semibold text-foreground'>
            {labels.title}
          </SheetTitle>
        </SheetHeader>

        <div className='flex-1 overflow-y-auto px-6 py-5'>
          {loading ? (
            <div className='flex h-40 items-center justify-center'>
              <Loading />
            </div>
          ) : null}

          {!loading && error ? (
            <ErrorDisplay
              errorCode={error.code || 0}
              errorMessage={error.message}
              onRetry={onRetry}
            />
          ) : null}

          {!loading && !error && detail ? (
            <div className='space-y-6'>
              <Section title={labels.basicInfoSection}>
                <DetailRow
                  label={labels.user}
                  value={primaryAccount}
                />
                <DetailRow
                  label={labels.nickname}
                  value={nickname}
                />
                {labels.userId ? (
                  <DetailRow
                    label={labels.userId}
                    value={formatDisplayValue(basicInfo?.user_bid, emptyValue)}
                  />
                ) : null}
                <DetailRow
                  label={resolveOutlineFieldLabel({
                    lessonTitle: basicInfo?.lesson_title,
                    chapterTitle: basicInfo?.chapter_title,
                  })}
                  value={resolveLessonDisplay({
                    lessonTitle: basicInfo?.lesson_title,
                    chapterTitle: basicInfo?.chapter_title,
                    emptyValue,
                  })}
                />
                <DetailRow
                  label={labels.followUpTime}
                  value={formatDisplayValue(
                    formatAdminUtcDateTime(basicInfo?.created_at),
                    emptyValue,
                  )}
                />
                <DetailRow
                  label={labels.turnIndex}
                  value={turnIndexLabel}
                />
                <p className='rounded-lg bg-muted/[0.16] px-3 py-2 text-xs leading-5 text-muted-foreground'>
                  {labels.turnIndexHelp}
                </p>
              </Section>

              <Section
                title={labels.currentRecordSection}
                description={labels.currentRecordHint}
              >
                {labels.sourceOutput ? (
                  <ExpandableTextBlock
                    title={labels.sourceOutput.title}
                    content={currentRecord?.source_output_content}
                    emptyValue={emptyValue}
                    emptyState={labels.sourceOutput.unavailable}
                    emphasizeEmptyState
                  />
                ) : null}
                <ExpandableTextBlock
                  title={labels.currentFollowUp}
                  content={currentRecord?.follow_up_content}
                  emptyValue={emptyValue}
                />
                <ExpandableTextBlock
                  title={labels.currentAnswer}
                  content={currentRecord?.answer_content}
                  emptyValue={emptyValue}
                />
              </Section>

              <Section title={labels.timelineSection}>
                <div className='space-y-3'>
                  {timeline.map((item, index) => (
                    <div
                      key={`${item.role}-${item.created_at}-${index}`}
                      className={cn(
                        'rounded-lg border border-border bg-white px-4 py-3 transition-colors',
                        item.is_current &&
                          'border-primary/50 bg-primary/[0.06] shadow-sm ring-1 ring-primary/15',
                      )}
                    >
                      <div className='mb-2 flex items-center justify-between gap-3'>
                        <div className='flex items-center gap-2'>
                          <Badge
                            variant='outline'
                            className={cn(
                              'rounded-full px-2.5 py-0.5 text-xs font-medium',
                              item.role === 'teacher'
                                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                : 'border-sky-200 bg-sky-50 text-sky-700',
                            )}
                          >
                            {resolveRoleLabel(item.role)}
                          </Badge>
                          {item.is_current ? (
                            <Badge className='rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/10'>
                              {labels.timelineCurrent}
                            </Badge>
                          ) : null}
                        </div>
                        <span className='text-xs text-muted-foreground'>
                          {formatDisplayValue(
                            formatAdminUtcDateTime(item.created_at),
                            emptyValue,
                          )}
                        </span>
                      </div>
                      <ExpandableTextBlock
                        content={item.content}
                        emptyValue={emptyValue}
                        variant='plain'
                      />
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
