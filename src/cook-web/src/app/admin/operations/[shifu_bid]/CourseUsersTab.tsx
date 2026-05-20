'use client';

import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { AdminPagination } from '@/app/admin/components/AdminPagination';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import { formatAdminNaiveDateTime } from '@/app/admin/lib/dateTime';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Label } from '@/components/ui/Label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { cn } from '@/lib/utils';
import type {
  AdminOperationCourseUserItem,
  AdminOperationCourseUsersResponse,
} from '../operation-course-types';
import type {
  CourseUserFilters,
  CourseUserPaymentStatus,
  UserColumnKey,
} from './courseUsersTabConfig';

function ClearableTextInput({
  value,
  placeholder,
  clearLabel,
  onChange,
}: {
  value: string;
  placeholder: string;
  clearLabel: string;
  onChange: (value: string) => void;
}) {
  const hasValue = value.trim().length > 0;

  return (
    <div className='flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-within:outline-none'>
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className='h-full min-w-0 flex-1 border-0 bg-transparent p-0 text-sm leading-none text-foreground placeholder:text-muted-foreground focus:outline-none'
      />
      {hasValue ? (
        <button
          type='button'
          aria-label={clearLabel}
          className='ml-2 shrink-0 rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground'
          onMouseDown={event => event.preventDefault()}
          onClick={() => onChange('')}
        >
          <X className='h-3.5 w-3.5' />
        </button>
      ) : null}
    </div>
  );
}

type ErrorState = { message: string; code?: number };

type CourseUsersTabProps = {
  filtersDraft: CourseUserFilters;
  loading: boolean;
  error: ErrorState | null;
  users: AdminOperationCourseUsersResponse;
  rows: AdminOperationCourseUserItem[];
  pageIndex: number;
  pageCount: number;
  contactKeywordPlaceholder: string;
  accountLabel: string;
  emptyValue: string;
  defaultUserName: string;
  locale: string;
  onKeywordChange: (value: string) => void;
  onUserRoleChange: (value: string) => void;
  onLearningStatusChange: (value: string) => void;
  onPaymentStatusChange: (value: CourseUserPaymentStatus) => void;
  onSearch: () => void;
  onReset: () => void;
  onPageChange: (nextPage: number) => void;
  resolveCourseUserRoleLabel: (
    userRole: AdminOperationCourseUserItem['user_role'],
  ) => string;
  resolveCourseUserLearningStatusLabel: (
    learningStatus: AdminOperationCourseUserItem['learning_status'],
  ) => string;
  resolveCourseUserPaidAmountDisplay: (
    courseUser: AdminOperationCourseUserItem,
  ) => string;
  resolveCourseUserAccount: (
    courseUser: AdminOperationCourseUserItem,
  ) => string;
  formatLearningProgress: (
    learnedLessonCount: number,
    totalLessonCount: number,
    locale: string,
  ) => string;
  getColumnStyle: (key: UserColumnKey) => {
    width: number;
    minWidth: number;
    maxWidth: number;
  };
  getResizeHandleProps: (key: UserColumnKey) => {
    onMouseDown: (event: React.MouseEvent<HTMLElement>) => void;
    'aria-hidden': 'true';
  };
};

export default function CourseUsersTab({
  filtersDraft,
  loading,
  error,
  users,
  rows,
  pageIndex,
  pageCount,
  contactKeywordPlaceholder,
  accountLabel,
  emptyValue,
  defaultUserName,
  locale,
  onKeywordChange,
  onUserRoleChange,
  onLearningStatusChange,
  onPaymentStatusChange,
  onSearch,
  onReset,
  onPageChange,
  resolveCourseUserRoleLabel,
  resolveCourseUserLearningStatusLabel,
  resolveCourseUserPaidAmountDisplay,
  resolveCourseUserAccount,
  formatLearningProgress,
  getColumnStyle,
  getResizeHandleProps,
}: CourseUsersTabProps) {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');

  const renderResizeHandle = (key: UserColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  return (
    <Card className='overflow-hidden border-border/80 shadow-sm ring-1 ring-border/40'>
      <CardContent className='space-y-3 px-6 py-6'>
        <form
          className='rounded-xl border border-border bg-muted/20 p-3'
          onSubmit={event => {
            event.preventDefault();
            onSearch();
          }}
        >
          <div className='grid gap-3 md:grid-cols-2 xl:grid-cols-4'>
            <div className='flex flex-col gap-2'>
              <Label className='text-xs font-medium text-muted-foreground'>
                {tOperations('detail.usersFilters.userKeyword')}
              </Label>
              <ClearableTextInput
                value={filtersDraft.keyword}
                placeholder={contactKeywordPlaceholder}
                clearLabel={t('module.chat.lessonFeedbackClearInput')}
                onChange={onKeywordChange}
              />
            </div>
            <div className='flex flex-col gap-2'>
              <Label className='text-xs font-medium text-muted-foreground'>
                {tOperations('detail.usersFilters.userRole')}
              </Label>
              <Select
                value={filtersDraft.userRole}
                onValueChange={onUserRoleChange}
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>
                    {tOperations('detail.usersFilters.all')}
                  </SelectItem>
                  <SelectItem value='operator'>
                    {resolveCourseUserRoleLabel('operator')}
                  </SelectItem>
                  <SelectItem value='creator'>
                    {resolveCourseUserRoleLabel('creator')}
                  </SelectItem>
                  <SelectItem value='student'>
                    {resolveCourseUserRoleLabel('student')}
                  </SelectItem>
                  <SelectItem value='normal'>
                    {resolveCourseUserRoleLabel('normal')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='flex flex-col gap-2'>
              <Label className='text-xs font-medium text-muted-foreground'>
                {tOperations('detail.usersFilters.learningStatus')}
              </Label>
              <Select
                value={filtersDraft.learningStatus}
                onValueChange={onLearningStatusChange}
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>
                    {tOperations('detail.usersFilters.all')}
                  </SelectItem>
                  <SelectItem value='not_started'>
                    {resolveCourseUserLearningStatusLabel('not_started')}
                  </SelectItem>
                  <SelectItem value='learning'>
                    {resolveCourseUserLearningStatusLabel('learning')}
                  </SelectItem>
                  <SelectItem value='completed'>
                    {resolveCourseUserLearningStatusLabel('completed')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='flex flex-col gap-2'>
              <Label className='text-xs font-medium text-muted-foreground'>
                {tOperations('detail.usersFilters.paymentStatus')}
              </Label>
              <Select
                value={filtersDraft.paymentStatus}
                onValueChange={value =>
                  onPaymentStatusChange(value as CourseUserPaymentStatus)
                }
              >
                <SelectTrigger className='h-9'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>
                    {tOperations('detail.usersFilters.all')}
                  </SelectItem>
                  <SelectItem value='paid'>
                    {tOperations('detail.usersFilters.paymentPaid')}
                  </SelectItem>
                  <SelectItem value='unpaid'>
                    {tOperations('detail.usersFilters.paymentUnpaid')}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className='mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4 xl:items-end'>
            <div className='pl-3 text-sm text-muted-foreground xl:self-center'>
              {tOperations('detail.usersCount', {
                count: users.total,
              })}
            </div>
            <div className='hidden xl:block' />
            <div className='hidden xl:block' />
            <div className='flex min-h-9 items-center justify-start gap-2 md:justify-end'>
              <Button
                type='button'
                variant='outline'
                className='h-9 px-4'
                onClick={onReset}
                disabled={loading}
              >
                {t('module.order.filters.reset')}
              </Button>
              <Button
                type='submit'
                className='h-9 px-4'
                disabled={loading}
              >
                {t('module.order.filters.search')}
              </Button>
            </div>
          </div>
        </form>

        <AdminTableShell
          loading={loading}
          isEmpty={!error && rows.length === 0}
          emptyContent={tOperations('detail.usersTable.empty')}
          emptyColSpan={11}
          withTooltipProvider={!error}
          tableWrapperClassName='overflow-auto'
          loadingClassName='min-h-[240px]'
          footer={
            pageCount > 1 ? (
              <AdminPagination
                pageIndex={pageIndex}
                pageCount={pageCount}
                onPageChange={onPageChange}
                prevLabel={t('module.order.paginationPrev')}
                nextLabel={t('module.order.paginationNext')}
                prevAriaLabel={t('module.order.paginationPrevAriaLabel')}
                nextAriaLabel={t('module.order.paginationNextAriaLabel')}
                className='mx-0 w-auto justify-end'
              />
            ) : null
          }
          table={
            error ? (
              <div className='flex min-h-[240px] items-center justify-center p-6 text-center'>
                <div className='space-y-2'>
                  <div className='text-sm font-medium text-destructive'>
                    {error.message}
                  </div>
                  {typeof error.code === 'number' ? (
                    <div className='text-xs text-muted-foreground'>
                      {error.code}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              emptyRow => (
                <Table className='table-auto'>
                  <TableHeader>
                    <TableRow>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('account')}
                      >
                        {accountLabel}
                        {renderResizeHandle('account')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('nickname')}
                      >
                        {tOperations('detail.usersTable.nickname')}
                        {renderResizeHandle('nickname')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('userRole')}
                      >
                        {tOperations('detail.usersTable.userRole')}
                        {renderResizeHandle('userRole')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('learningProgress')}
                      >
                        {tOperations('detail.usersTable.learningProgress')}
                        {renderResizeHandle('learningProgress')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('learningStatus')}
                      >
                        {tOperations('detail.usersTable.learningStatus')}
                        {renderResizeHandle('learningStatus')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('isPaid')}
                      >
                        {tOperations('detail.usersTable.isPaid')}
                        {renderResizeHandle('isPaid')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('totalPaidAmount')}
                      >
                        {tOperations('detail.usersTable.totalPaidAmount')}
                        {renderResizeHandle('totalPaidAmount')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('lastLearnedAt')}
                      >
                        {tOperations('detail.usersTable.lastLearnedAt')}
                        {renderResizeHandle('lastLearnedAt')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('lastLoginAt')}
                      >
                        {tOperations('detail.usersTable.lastLoginAt')}
                        {renderResizeHandle('lastLoginAt')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                          'h-10 whitespace-nowrap bg-muted/80 text-xs',
                        )}
                        style={getColumnStyle('joinedAt')}
                      >
                        {tOperations('detail.usersTable.joinedAt')}
                        {renderResizeHandle('joinedAt')}
                      </TableHead>
                      <TableHead
                        className={cn(
                          getAdminStickyRightHeaderClass(
                            'h-10 whitespace-nowrap text-center text-xs',
                          ),
                        )}
                        style={getColumnStyle('action')}
                      >
                        {tOperations('detail.usersTable.action')}
                        {renderResizeHandle('action')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {emptyRow}
                    {rows.map(row => (
                      <TableRow key={row.user_bid}>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-sm text-foreground last:border-r-0'
                          style={getColumnStyle('account')}
                        >
                          <AdminTooltipText
                            text={resolveCourseUserAccount(row)}
                            emptyValue={emptyValue}
                            className='mx-auto block max-w-[180px] font-semibold text-foreground'
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-sm text-foreground last:border-r-0'
                          style={getColumnStyle('nickname')}
                        >
                          <AdminTooltipText
                            text={row.nickname || defaultUserName}
                            emptyValue={emptyValue}
                            className='mx-auto block max-w-[140px]'
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center last:border-r-0'
                          style={getColumnStyle('userRole')}
                        >
                          <Badge
                            variant='outline'
                            className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                          >
                            {resolveCourseUserRoleLabel(row.user_role)}
                          </Badge>
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-sm text-foreground last:border-r-0'
                          style={getColumnStyle('learningProgress')}
                        >
                          <span className='font-medium tabular-nums text-foreground'>
                            {formatLearningProgress(
                              row.learned_lesson_count,
                              row.total_lesson_count,
                              locale,
                            )}
                          </span>
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center last:border-r-0'
                          style={getColumnStyle('learningStatus')}
                        >
                          <Badge
                            variant='outline'
                            className='border-0 bg-transparent px-0 py-0 text-xs font-medium text-foreground shadow-none'
                          >
                            {resolveCourseUserLearningStatusLabel(
                              row.learning_status,
                            )}
                          </Badge>
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-xs font-medium text-muted-foreground/80 last:border-r-0'
                          style={getColumnStyle('isPaid')}
                        >
                          {row.is_paid
                            ? tOperations('detail.boolean.yes')
                            : tOperations('detail.boolean.no')}
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-sm text-foreground last:border-r-0'
                          style={getColumnStyle('totalPaidAmount')}
                        >
                          <span className='font-medium tabular-nums text-foreground'>
                            {resolveCourseUserPaidAmountDisplay(row)}
                          </span>
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-xs text-muted-foreground/65 last:border-r-0'
                          style={getColumnStyle('lastLearnedAt')}
                        >
                          <AdminTooltipText
                            text={formatAdminNaiveDateTime(
                              row.last_learning_at,
                            )}
                            emptyValue={emptyValue}
                            className='mx-auto block max-w-full tabular-nums'
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-xs text-muted-foreground/65 last:border-r-0'
                          style={getColumnStyle('lastLoginAt')}
                        >
                          <AdminTooltipText
                            text={formatAdminNaiveDateTime(row.last_login_at)}
                            emptyValue={emptyValue}
                            className='mx-auto block max-w-full tabular-nums'
                          />
                        </TableCell>
                        <TableCell
                          className='border-r border-border py-2.5 text-center text-xs text-muted-foreground/65 last:border-r-0'
                          style={getColumnStyle('joinedAt')}
                        >
                          <AdminTooltipText
                            text={formatAdminNaiveDateTime(row.joined_at)}
                            emptyValue={emptyValue}
                            className='mx-auto block max-w-full tabular-nums'
                          />
                        </TableCell>
                        <TableCell
                          className={getAdminStickyRightCellClass(
                            'py-2.5 text-center text-sm text-muted-foreground/80',
                          )}
                          style={getColumnStyle('action')}
                        >
                          {emptyValue}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )
            )
          }
        />
      </CardContent>
    </Card>
  );
}
