import Link from 'next/link';
import type { CSSProperties, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminRowActions from '@/app/admin/components/AdminRowActions';
import { formatAdminUtcDateTime } from '@/app/admin/lib/dateTime';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  getAdminStickyRightCellClass,
  getAdminStickyRightHeaderClass,
} from '@/app/admin/components/adminTableStyles';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import { buildAdminOperationsCourseDetailUrl } from './operation-course-routes';
import type { AdminOperationCourseItem } from './operation-course-types';
import {
  DEFAULT_COLUMN_WIDTHS,
  type ColumnKey,
  renderTooltipText,
  TABLE_INLINE_ACTION_BUTTON_CLASS,
} from './operationCoursePageShared';

type ActorDisplay = {
  primary: string;
  secondary: string;
};

type CourseTableSectionProps = {
  loading: boolean;
  courses: AdminOperationCourseItem[];
  pageIndex: number;
  pageCount: number;
  getColumnStyle: (key: ColumnKey) => CSSProperties;
  renderResizeHandle: (key: ColumnKey) => ReactNode;
  resolveActorDisplay: (
    course: AdminOperationCourseItem,
    kind: 'creator' | 'updater',
  ) => ActorDisplay;
  resolveCourseStatusLabel: (status?: string) => string;
  formatMoney: (value?: string) => string;
  onPageChange: (page: number) => void;
  onPromptDetailClick: (course: AdminOperationCourseItem) => Promise<void>;
  onCopyCourseClick: (course: AdminOperationCourseItem) => void;
  onTransferCreatorClick: (course: AdminOperationCourseItem) => void;
};

export default function CourseTableSection({
  loading,
  courses,
  pageIndex,
  pageCount,
  getColumnStyle,
  renderResizeHandle,
  resolveActorDisplay,
  resolveCourseStatusLabel,
  formatMoney,
  onPageChange,
  onPromptDetailClick,
  onCopyCourseClick,
  onTransferCreatorClick,
}: CourseTableSectionProps) {
  const { t } = useTranslation();
  const { t: tOperations } = useTranslation('module.operationsCourse');

  return (
    <AdminTableShell
      loading={loading}
      isEmpty={courses.length === 0}
      emptyContent={tOperations('emptyList')}
      emptyColSpan={Object.keys(DEFAULT_COLUMN_WIDTHS).length}
      withTooltipProvider
      tableWrapperClassName='max-h-[calc(100vh-18rem)] overflow-auto'
      table={emptyRow => (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('courseId')}
              >
                {tOperations('table.courseId')}
                {renderResizeHandle('courseId')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('courseName')}
              >
                {tOperations('table.courseName')}
                {renderResizeHandle('courseName')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('status')}
              >
                {tOperations('table.status')}
                {renderResizeHandle('status')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('price')}
              >
                {tOperations('table.price')}
                {renderResizeHandle('price')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('model')}
              >
                {tOperations('table.model')}
                {renderResizeHandle('model')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('coursePrompt')}
              >
                {tOperations('table.coursePrompt')}
                {renderResizeHandle('coursePrompt')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('creator')}
              >
                {tOperations('table.creator')}
                {renderResizeHandle('creator')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('modifier')}
              >
                {tOperations('table.modifier')}
                {renderResizeHandle('modifier')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('updatedAt')}
              >
                {tOperations('table.updatedAt')}
                {renderResizeHandle('updatedAt')}
              </TableHead>
              <TableHead
                className={ADMIN_TABLE_HEADER_CELL_CENTER_CLASS}
                style={getColumnStyle('createdAt')}
              >
                {tOperations('table.createdAt')}
                {renderResizeHandle('createdAt')}
              </TableHead>
              <TableHead
                className={getAdminStickyRightHeaderClass('text-center')}
                style={getColumnStyle('action')}
              >
                {tOperations('table.action')}
                {renderResizeHandle('action')}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {emptyRow}
            {courses.map(course => {
              const creatorDisplay = resolveActorDisplay(course, 'creator');
              const updaterDisplay = resolveActorDisplay(course, 'updater');
              const detailUrl = buildAdminOperationsCourseDetailUrl(
                course.shifu_bid,
              );

              return (
                <TableRow key={course.shifu_bid}>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('courseId')}
                  >
                    {renderTooltipText(course.shifu_bid, 'mx-auto block')}
                  </TableCell>
                  <TableCell
                    className='whitespace-nowrap border-r border-border last:border-r-0 overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('courseName')}
                  >
                    {detailUrl ? (
                      <Link
                        href={detailUrl}
                        target='_blank'
                        rel='noopener noreferrer'
                        className='mx-auto block max-w-full text-center text-primary transition-colors hover:text-primary/80 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
                      >
                        {renderTooltipText(
                          course.course_name,
                          'truncate text-center',
                        )}
                      </Link>
                    ) : (
                      renderTooltipText(
                        course.course_name,
                        'truncate text-center',
                      )
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('status')}
                  >
                    {renderTooltipText(
                      resolveCourseStatusLabel(course.course_status),
                      'mx-auto block text-foreground',
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('price')}
                  >
                    {renderTooltipText(
                      formatMoney(course.price),
                      'mx-auto block text-foreground',
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('model')}
                  >
                    {renderTooltipText(
                      course.course_model,
                      'mx-auto block text-foreground',
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('coursePrompt')}
                  >
                    {course.has_course_prompt ? (
                      <button
                        type='button'
                        className='text-primary transition-colors hover:text-primary/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-2'
                        onClick={() => void onPromptDetailClick(course)}
                      >
                        {tOperations('table.detailAction')}
                      </button>
                    ) : (
                      renderTooltipText(undefined, 'text-foreground')
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('creator')}
                  >
                    <div className='flex flex-col items-center gap-0.5 leading-tight'>
                      {renderTooltipText(
                        creatorDisplay.primary,
                        'mx-auto block text-foreground whitespace-nowrap text-center',
                      )}
                      {creatorDisplay.secondary
                        ? renderTooltipText(
                            creatorDisplay.secondary,
                            'mx-auto block text-xs text-muted-foreground text-center',
                          )
                        : null}
                    </div>
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('modifier')}
                  >
                    <div className='flex flex-col items-center gap-0.5 leading-tight'>
                      {renderTooltipText(
                        updaterDisplay.primary,
                        'mx-auto block text-foreground whitespace-nowrap text-center',
                      )}
                      {updaterDisplay.secondary
                        ? renderTooltipText(
                            updaterDisplay.secondary,
                            'mx-auto block text-xs text-muted-foreground text-center',
                          )
                        : null}
                    </div>
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('updatedAt')}
                  >
                    {renderTooltipText(
                      formatAdminUtcDateTime(course.updated_at),
                      'mx-auto block',
                    )}
                  </TableCell>
                  <TableCell
                    className='border-r border-border last:border-r-0 whitespace-nowrap overflow-hidden text-center text-ellipsis'
                    style={getColumnStyle('createdAt')}
                  >
                    {renderTooltipText(
                      formatAdminUtcDateTime(course.created_at),
                      'mx-auto block',
                    )}
                  </TableCell>
                  <TableCell
                    className={getAdminStickyRightCellClass(
                      'whitespace-nowrap text-center',
                    )}
                    style={getColumnStyle('action')}
                  >
                    <div className='flex justify-center'>
                      <AdminRowActions
                        label={t('common.core.more')}
                        className={TABLE_INLINE_ACTION_BUTTON_CLASS}
                        actions={[
                          {
                            key: 'copy',
                            label: tOperations('actions.copyCourse'),
                            onClick: () => onCopyCourseClick(course),
                          },
                          {
                            key: 'transfer',
                            label: tOperations('actions.transferCreator'),
                            onClick: () => onTransferCreatorClick(course),
                          },
                        ]}
                      />
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
      pagination={{
        pageIndex,
        pageCount,
        onPageChange,
        prevLabel: t('module.order.paginationPrev'),
        nextLabel: t('module.order.paginationNext'),
        prevAriaLabel: t('module.order.paginationPrevAriaLabel'),
        nextAriaLabel: t('module.order.paginationNextAriaLabel'),
      }}
    />
  );
}
