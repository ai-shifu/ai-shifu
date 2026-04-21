'use client';

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
import { cn } from '@/lib/utils';
import type { AdminOperationCourseFollowUpDetailResponse } from '../../operation-course-types';

type ErrorState = { message: string; code?: number };

type ContactMode = 'phone' | 'email';

type FollowUpDetailSheetProps = {
  open: boolean;
  detail: AdminOperationCourseFollowUpDetailResponse | null;
  loading: boolean;
  error: ErrorState | null;
  emptyValue: string;
  contactMode: ContactMode;
  defaultUserName: string;
  resolveLessonDisplay: (values: {
    lessonTitle?: string;
    chapterTitle?: string;
    emptyValue: string;
  }) => string;
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

const formatValue = (value: string | undefined | null, emptyValue: string) => {
  const normalizedValue = value?.trim() || '';
  return normalizedValue || emptyValue;
};

const resolvePrimaryAccount = ({
  mobile,
  email,
  userBid,
  contactMode,
  emptyValue,
}: {
  mobile?: string;
  email?: string;
  userBid?: string;
  contactMode: ContactMode;
  emptyValue: string;
}) => {
  const preferred = contactMode === 'email' ? email : mobile;
  const alternate = contactMode === 'email' ? mobile : email;
  return formatValue(preferred || alternate || userBid, emptyValue);
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

/**
 * t('module.operationsCourse.detail.followUps.drawer.title')
 * t('module.operationsCourse.detail.followUps.drawer.sections.basicInfo')
 * t('module.operationsCourse.detail.followUps.drawer.sections.currentRecord')
 * t('module.operationsCourse.detail.followUps.drawer.sections.timeline')
 * t('module.operationsCourse.detail.followUps.drawer.currentRecordHint')
 * t('module.operationsCourse.detail.followUps.drawer.fields.user')
 * t('module.operationsCourse.detail.followUps.drawer.fields.nickname')
 * t('module.operationsCourse.detail.followUps.drawer.fields.userId')
 * t('module.operationsCourse.detail.followUps.drawer.fields.chapter')
 * t('module.operationsCourse.detail.followUps.drawer.fields.followUpTime')
 * t('module.operationsCourse.detail.followUps.drawer.fields.turnIndex')
 * t('module.operationsCourse.detail.followUps.drawer.fields.sourceOutput')
 * t('module.operationsCourse.detail.followUps.drawer.fields.currentFollowUp')
 * t('module.operationsCourse.detail.followUps.drawer.fields.currentAnswer')
 * t('module.operationsCourse.detail.followUps.drawer.sourceUnavailable')
 * t('module.operationsCourse.detail.followUps.drawer.timeline.student')
 * t('module.operationsCourse.detail.followUps.drawer.timeline.teacher')
 * t('module.operationsCourse.detail.followUps.drawer.timeline.current')
 * t('module.operationsCourse.detail.followUps.turnIndexHelp')
 * t('module.operationsCourse.detail.followUps.emptyValue')
 */
export default function FollowUpDetailSheet({
  open,
  detail,
  loading,
  error,
  emptyValue,
  contactMode,
  defaultUserName,
  resolveLessonDisplay,
  onRetry,
  onOpenChange,
}: FollowUpDetailSheetProps) {
  const { t } = useTranslation('module.operationsCourse');

  const basicInfo = detail?.basic_info;
  const currentRecord = detail?.current_record;
  const timeline = detail?.timeline || [];

  const primaryAccount = useMemo(
    () =>
      resolvePrimaryAccount({
        mobile: basicInfo?.mobile,
        email: basicInfo?.email,
        userBid: basicInfo?.user_bid,
        contactMode,
        emptyValue,
      }),
    [
      basicInfo?.email,
      basicInfo?.mobile,
      basicInfo?.user_bid,
      contactMode,
      emptyValue,
    ],
  );
  const nickname = useMemo(() => {
    const normalizedNickname = basicInfo?.nickname?.trim() || '';
    if (!normalizedNickname || normalizedNickname === defaultUserName) {
      return emptyValue;
    }
    return normalizedNickname;
  }, [basicInfo?.nickname, defaultUserName, emptyValue]);
  const turnIndexLabel = useMemo(() => {
    if (!basicInfo?.turn_index) {
      return emptyValue;
    }
    return t('detail.followUps.turnIndex', { count: basicInfo.turn_index });
  }, [basicInfo?.turn_index, emptyValue, t]);
  const sourceOutputFallback = t('detail.followUps.drawer.sourceUnavailable');

  const roleLabelMap = useMemo(
    () => ({
      student: t('detail.followUps.drawer.timeline.student'),
      teacher: t('detail.followUps.drawer.timeline.teacher'),
    }),
    [t],
  );

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
    >
      <SheetContent className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[420px] md:w-[520px] lg:w-[640px]'>
        <SheetHeader className='border-b border-border px-6 py-4 pr-12'>
          <SheetTitle className='text-base font-semibold text-foreground'>
            {t('detail.followUps.drawer.title')}
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
              <Section title={t('detail.followUps.drawer.sections.basicInfo')}>
                <DetailRow
                  label={t('detail.followUps.drawer.fields.user')}
                  value={primaryAccount}
                />
                <DetailRow
                  label={t('detail.followUps.drawer.fields.nickname')}
                  value={nickname}
                />
                <DetailRow
                  label={t('detail.followUps.drawer.fields.userId')}
                  value={formatValue(basicInfo?.user_bid, emptyValue)}
                />
                <DetailRow
                  label={t('detail.followUps.drawer.fields.chapter')}
                  value={resolveLessonDisplay({
                    lessonTitle: basicInfo?.lesson_title,
                    chapterTitle: basicInfo?.chapter_title,
                    emptyValue,
                  })}
                />
                <DetailRow
                  label={t('detail.followUps.drawer.fields.followUpTime')}
                  value={formatValue(basicInfo?.created_at, emptyValue)}
                />
                <DetailRow
                  label={t('detail.followUps.drawer.fields.turnIndex')}
                  value={turnIndexLabel}
                />
                <p className='rounded-lg bg-muted/[0.16] px-3 py-2 text-xs leading-5 text-muted-foreground'>
                  {t('detail.followUps.turnIndexHelp')}
                </p>
              </Section>

              <Section
                title={t('detail.followUps.drawer.sections.currentRecord')}
                description={t('detail.followUps.drawer.currentRecordHint')}
              >
                <ExpandableTextBlock
                  title={t('detail.followUps.drawer.fields.sourceOutput')}
                  content={currentRecord?.source_output_content}
                  emptyValue={emptyValue}
                  emptyState={sourceOutputFallback}
                  emphasizeEmptyState
                />
                <ExpandableTextBlock
                  title={t('detail.followUps.drawer.fields.currentFollowUp')}
                  content={currentRecord?.follow_up_content}
                  emptyValue={emptyValue}
                />
                <ExpandableTextBlock
                  title={t('detail.followUps.drawer.fields.currentAnswer')}
                  content={currentRecord?.answer_content}
                  emptyValue={emptyValue}
                />
              </Section>

              <Section title={t('detail.followUps.drawer.sections.timeline')}>
                <div className='space-y-3'>
                  {timeline.map((item, index) => {
                    const roleLabel =
                      roleLabelMap[item.role as 'student' | 'teacher'] ||
                      item.role;
                    return (
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
                              {roleLabel}
                            </Badge>
                            {item.is_current ? (
                              <Badge className='rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/10'>
                                {t('detail.followUps.drawer.timeline.current')}
                              </Badge>
                            ) : null}
                          </div>
                          <span className='text-xs text-muted-foreground'>
                            {formatValue(item.created_at, emptyValue)}
                          </span>
                        </div>
                        <ExpandableTextBlock
                          content={item.content}
                          emptyValue={emptyValue}
                          variant='plain'
                        />
                      </div>
                    );
                  })}
                </div>
              </Section>
            </div>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
