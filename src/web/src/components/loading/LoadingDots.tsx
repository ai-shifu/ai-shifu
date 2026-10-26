import type { CSSProperties, HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

const DEFAULT_DOT_COUNT = 4;
const DEFAULT_DOT_SIZE = 12;
const DEFAULT_DOT_GAP = 12;
const DEFAULT_DURATION_MS = 900;
const DEFAULT_ACTIVE_SCALE = 1.7;
const DEFAULT_REST_OPACITY = 0.32;

type LoadingDotsCssVariables = CSSProperties & {
  '--loading-dot-active-scale'?: number;
  '--loading-dot-duration'?: string;
  '--loading-dot-rest-opacity'?: number;
};

export interface LoadingDotsProps extends Omit<
  HTMLAttributes<HTMLDivElement>,
  'children'
> {
  ariaLabel?: string;
  count?: number;
  dotClassName?: string;
  durationMs?: number;
  gap?: number;
  restOpacity?: number;
  size?: number;
  activeScale?: number;
}

const normalizePositiveNumber = (value: number, fallback: number) =>
  Number.isFinite(value) && value > 0 ? value : fallback;

const createDotIndexes = (count: number) =>
  Array.from(
    {
      length: Math.max(
        1,
        Math.floor(normalizePositiveNumber(count, DEFAULT_DOT_COUNT)),
      ),
    },
    (_, index) => index,
  );

export default function LoadingDots({
  activeScale = DEFAULT_ACTIVE_SCALE,
  ariaLabel,
  className,
  count = DEFAULT_DOT_COUNT,
  dotClassName,
  durationMs = DEFAULT_DURATION_MS,
  gap = DEFAULT_DOT_GAP,
  restOpacity = DEFAULT_REST_OPACITY,
  size = DEFAULT_DOT_SIZE,
  style,
  ...props
}: LoadingDotsProps) {
  const dotIndexes = createDotIndexes(count);
  const safeDurationMs = normalizePositiveNumber(
    durationMs,
    DEFAULT_DURATION_MS,
  );
  const safeGap = normalizePositiveNumber(gap, DEFAULT_DOT_GAP);
  const safeSize = normalizePositiveNumber(size, DEFAULT_DOT_SIZE);
  const safeActiveScale = normalizePositiveNumber(
    activeScale,
    DEFAULT_ACTIVE_SCALE,
  );
  const safeRestOpacity = Math.min(
    1,
    Math.max(0.05, normalizePositiveNumber(restOpacity, DEFAULT_REST_OPACITY)),
  );
  const animationStep = safeDurationMs / dotIndexes.length;
  const containerStyle: CSSProperties = {
    gap: `${safeGap}px`,
    ...style,
  };

  return (
    <div
      aria-hidden={ariaLabel ? undefined : true}
      aria-label={ariaLabel}
      className={cn('inline-flex items-center justify-center', className)}
      role={ariaLabel ? 'status' : undefined}
      style={containerStyle}
      {...props}
    >
      {dotIndexes.map(index => {
        const dotStyle: LoadingDotsCssVariables = {
          width: `${safeSize}px`,
          height: `${safeSize}px`,
          animationDelay: `${animationStep * index}ms`,
          '--loading-dot-active-scale': safeActiveScale,
          '--loading-dot-duration': `${safeDurationMs}ms`,
          '--loading-dot-rest-opacity': safeRestOpacity,
        };

        return (
          <span
            aria-hidden='true'
            className={cn(
              'inline-block rounded-full bg-primary animate-loading-dot-bounce will-change-transform',
              dotClassName,
            )}
            key={index}
            style={dotStyle}
          />
        );
      })}
    </div>
  );
}
