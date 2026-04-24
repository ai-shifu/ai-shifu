import { memo } from 'react';
import { cn } from '@/lib/utils';
import { useShallow } from 'zustand/react/shallow';
import { useCourseStore } from '@/c-store';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';

interface CourseHeaderSummaryProps {
  courseAvatar?: string;
  courseName?: string;
  className?: string;
  avatarClassName?: string;
  titleClassName?: string;
}

export const CourseHeaderSummary = ({
  courseAvatar,
  courseName,
  className,
  avatarClassName,
  titleClassName,
}: CourseHeaderSummaryProps) => {
  const { storedCourseAvatar, storedCourseName } = useCourseStore(
    useShallow(state => ({
      storedCourseAvatar: state.courseAvatar,
      storedCourseName: state.courseName,
    })),
  );
  const avatarSrc = courseAvatar ?? storedCourseAvatar ?? '';
  const title = courseName ?? storedCourseName ?? '';

  return (
    <div className={cn('flex min-w-0 flex-1 items-center', className)}>
      {avatarSrc ? (
        <Avatar className={cn('mr-2 h-8 w-8 shrink-0', avatarClassName)}>
          <AvatarImage
            src={avatarSrc}
            alt=''
          />
        </Avatar>
      ) : null}
      <span
        className={cn(
          'min-w-0 truncate text-[16px] font-semibold leading-[14px] text-black/80',
          titleClassName,
        )}
        title={title}
      >
        {title}
      </span>
    </div>
  );
};

export default memo(CourseHeaderSummary);
