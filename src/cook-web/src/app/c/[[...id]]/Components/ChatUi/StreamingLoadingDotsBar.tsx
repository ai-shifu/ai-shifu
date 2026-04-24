import { LoadingDots } from '@/components/loading';

export default function StreamingLoadingDotsBar() {
  return (
    <span className='inline-flex items-center py-1'>
      <LoadingDots
        count={4}
        durationMs={960}
        dotClassName='bg-muted-foreground'
        gap={6}
        restOpacity={0.2}
        size={6}
      />
    </span>
  );
}
