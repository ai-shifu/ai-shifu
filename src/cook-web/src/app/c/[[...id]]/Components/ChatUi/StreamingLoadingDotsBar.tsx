import { LoadingDots } from '@/components/loading';

export default function StreamingLoadingDotsBar() {
  return (
    <span className='inline-flex items-center py-1'>
      <LoadingDots
        count={4}
        durationMs={960}
        gap={10}
        size={10}
      />
    </span>
  );
}
