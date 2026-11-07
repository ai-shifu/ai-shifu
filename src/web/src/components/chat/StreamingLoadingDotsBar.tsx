import { LoadingDots } from '@/components/loading';

export default function StreamingLoadingDotsBar() {
  return (
    <span className='inline-flex items-center'>
      <LoadingDots
        count={4}
        durationMs={960}
        dotClassName='bg-primary'
        gap={5}
        restOpacity={0.2}
        size={5}
      />
    </span>
  );
}
