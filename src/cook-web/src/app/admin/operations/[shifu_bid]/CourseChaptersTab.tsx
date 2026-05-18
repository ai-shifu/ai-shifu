'use client';

import { Badge } from '@/components/ui/Badge';
import { Card, CardContent } from '@/components/ui/Card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table';
import AdminTableShell from '@/app/admin/components/AdminTableShell';
import AdminTooltipText from '@/app/admin/components/AdminTooltipText';
import {
  ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
  ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
  ADMIN_TABLE_RESIZE_HANDLE_CLASS,
} from '@/app/admin/components/adminTableStyles';
import { cn } from '@/lib/utils';
import type { AdminOperationCourseDetailChapter } from '../operation-course-types';

export type FlattenedChapterRow = AdminOperationCourseDetailChapter & {
  depth: number;
};

type ChapterColumnKey =
  | 'position'
  | 'name'
  | 'learningPermission'
  | 'visibility'
  | 'contentStatus'
  | 'modifier'
  | 'updatedAt'
  | 'contentDetail'
  | 'followUpCount'
  | 'ratingScore'
  | 'ratingCount';

type CourseChaptersTabProps = {
  rows: FlattenedChapterRow[];
  emptyValue: string;
  locale: string;
  onOpenChapterDetail: (chapter: FlattenedChapterRow) => void;
  resolveChapterTypeLabel: (nodeType?: string) => string;
  resolveLearningPermissionLabel: (permission?: string) => string;
  resolveContentStatusLabel: (contentStatus?: string) => string;
  resolveModifierDisplay: (chapter: FlattenedChapterRow) => {
    primary: string;
    secondary: string;
  };
  formatCount: (value: number, locale: string) => string;
  formatAdminNaiveDateTime: (value?: string) => string;
  getColumnStyle: (key: ChapterColumnKey) => {
    width: number;
    minWidth: number;
    maxWidth: number;
  };
  getResizeHandleProps: (key: ChapterColumnKey) => {
    onMouseDown: (event: React.MouseEvent<HTMLElement>) => void;
    'aria-hidden': 'true';
  };
  tOperations: (key: string) => string;
};

export default function CourseChaptersTab({
  rows,
  emptyValue,
  locale,
  onOpenChapterDetail,
  resolveChapterTypeLabel,
  resolveLearningPermissionLabel,
  resolveContentStatusLabel,
  resolveModifierDisplay,
  formatCount,
  formatAdminNaiveDateTime,
  getColumnStyle,
  getResizeHandleProps,
  tOperations,
}: CourseChaptersTabProps) {
  const renderResizeHandle = (key: ChapterColumnKey) => (
    <span
      className={ADMIN_TABLE_RESIZE_HANDLE_CLASS}
      {...getResizeHandleProps(key)}
    />
  );

  return (
    <Card className='border-border/80 shadow-sm ring-1 ring-border/40'>
      <CardContent className='pt-6'>
        <AdminTableShell
          loading={false}
          isEmpty={rows.length === 0}
          emptyContent={tOperations('detail.chaptersTable.empty')}
          emptyColSpan={11}
          withTooltipProvider
          tableWrapperClassName='overflow-auto'
          table={emptyRow => (
            <Table className='table-auto'>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('position')}
                  >
                    {tOperations('detail.chaptersTable.position')}
                    {renderResizeHandle('position')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('name')}
                  >
                    {tOperations('detail.chaptersTable.name')}
                    {renderResizeHandle('name')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('learningPermission')}
                  >
                    {tOperations('detail.chaptersTable.learningPermission')}
                    {renderResizeHandle('learningPermission')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('visibility')}
                  >
                    {tOperations('detail.chaptersTable.visibility')}
                    {renderResizeHandle('visibility')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('contentStatus')}
                  >
                    {tOperations('detail.chaptersTable.contentStatus')}
                    {renderResizeHandle('contentStatus')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('contentDetail')}
                  >
                    {tOperations('detail.chaptersTable.contentDetail')}
                    {renderResizeHandle('contentDetail')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('modifier')}
                  >
                    {tOperations('detail.chaptersTable.modifier')}
                    {renderResizeHandle('modifier')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('updatedAt')}
                  >
                    {tOperations('detail.chaptersTable.updatedAt')}
                    {renderResizeHandle('updatedAt')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap border-l-2 border-l-border/80 bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('followUpCount')}
                  >
                    {tOperations('detail.chaptersTable.followUpCount')}
                    {renderResizeHandle('followUpCount')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('ratingScore')}
                  >
                    {tOperations('detail.chaptersTable.ratingScore')}
                    {renderResizeHandle('ratingScore')}
                  </TableHead>
                  <TableHead
                    className={cn(
                      ADMIN_TABLE_HEADER_LAST_CELL_CENTER_CLASS,
                      'h-10 whitespace-nowrap bg-muted/80 text-xs',
                    )}
                    style={getColumnStyle('ratingCount')}
                  >
                    {tOperations('detail.chaptersTable.ratingCount')}
                    {renderResizeHandle('ratingCount')}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emptyRow}
                {rows.map(chapter => {
                  const {
                    primary: modifierPrimary,
                    secondary: modifierSecondary,
                  } = resolveModifierDisplay(chapter);

                  return (
                    <TableRow key={chapter.outline_item_bid}>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/80 last:border-r-0'
                        style={getColumnStyle('position')}
                      >
                        {chapter.position || emptyValue}
                      </TableCell>
                      <TableCell
                        className='border-r border-border py-2.5 last:border-r-0'
                        style={getColumnStyle('name')}
                      >
                        <div
                          className='flex min-w-0 items-center justify-center gap-2'
                          style={{ paddingLeft: `${chapter.depth * 20}px` }}
                        >
                          <Badge
                            variant='outline'
                            className='shrink-0 rounded-full border-border/60 bg-background px-1.5 py-0 text-[10px] font-medium text-muted-foreground'
                          >
                            {resolveChapterTypeLabel(chapter.node_type)}
                          </Badge>
                          <AdminTooltipText
                            text={chapter.title || emptyValue}
                            emptyValue={emptyValue}
                            className='text-center text-sm font-medium text-foreground'
                          />
                        </div>
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('learningPermission')}
                      >
                        {resolveLearningPermissionLabel(
                          chapter.learning_permission,
                        )}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('visibility')}
                      >
                        {chapter.is_visible
                          ? tOperations('detail.visibility.visible')
                          : tOperations('detail.visibility.hidden')}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('contentStatus')}
                      >
                        {resolveContentStatusLabel(chapter.content_status)}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center last:border-r-0'
                        style={getColumnStyle('contentDetail')}
                      >
                        <button
                          type='button'
                          className='text-sm text-primary transition-colors hover:text-primary/80'
                          onClick={() => onOpenChapterDetail(chapter)}
                        >
                          {tOperations('detail.chaptersTable.detailAction')}
                        </button>
                      </TableCell>
                      <TableCell
                        className='border-r border-border py-2.5 text-center last:border-r-0'
                        style={getColumnStyle('modifier')}
                      >
                        <div className='flex flex-col gap-0.5 leading-tight'>
                          <AdminTooltipText
                            text={modifierPrimary}
                            emptyValue={emptyValue}
                            className='text-sm text-foreground'
                          />
                          {modifierSecondary ? (
                            <AdminTooltipText
                              text={modifierSecondary}
                              emptyValue={emptyValue}
                              className='text-xs text-muted-foreground'
                            />
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('updatedAt')}
                      >
                        <AdminTooltipText
                          text={
                            formatAdminNaiveDateTime(chapter.updated_at) ||
                            emptyValue
                          }
                          emptyValue={emptyValue}
                          className='mx-auto block max-w-full'
                        />
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-l-2 border-l-border/80 border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('followUpCount')}
                      >
                        {chapter.node_type === 'chapter'
                          ? emptyValue
                          : formatCount(chapter.follow_up_count, locale)}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap border-r border-border py-2.5 text-center text-sm text-muted-foreground/75 last:border-r-0'
                        style={getColumnStyle('ratingScore')}
                      >
                        {chapter.node_type === 'chapter'
                          ? emptyValue
                          : chapter.rating_score || emptyValue}
                      </TableCell>
                      <TableCell
                        className='whitespace-nowrap py-2.5 text-center text-sm text-muted-foreground/75'
                        style={getColumnStyle('ratingCount')}
                      >
                        {chapter.node_type === 'chapter'
                          ? emptyValue
                          : formatCount(chapter.rating_count, locale)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        />
      </CardContent>
    </Card>
  );
}
