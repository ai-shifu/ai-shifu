import React from 'react';
import { OnboardingCard } from './OnboardingCard';

type RectLike = {
  top: number;
  left: number;
  width: number;
  height: number;
};

type OnboardingOverlayProps = {
  open: boolean;
  advanceAriaLabel: string;
  title: React.ReactNode;
  description: React.ReactNode;
  stepIndex: number;
  totalSteps: number;
  continueLabel: React.ReactNode;
  actionLabel?: React.ReactNode;
  actionHref?: string;
  targetRect: RectLike | null;
  highlightPadding?: number;
  onAdvance: () => void;
};

const PADDING = 10;
const HIGHLIGHT_RADIUS = 16;
const OVERLAY_BG = 'rgba(15,23,42,0.62)';
const DEFAULT_CARD_WIDTH = 340;
const DEFAULT_CARD_HEIGHT = 220;
const CARD_GAP = 18;
const VIEWPORT_MARGIN = 8;

function buildCardPosition(
  targetRect: RectLike | null,
  cardSize: { width: number; height: number },
): React.CSSProperties {
  if (typeof window === 'undefined') {
    return { left: VIEWPORT_MARGIN, top: VIEWPORT_MARGIN };
  }

  const maxLeft = Math.max(
    window.innerWidth - cardSize.width - VIEWPORT_MARGIN,
    VIEWPORT_MARGIN,
  );
  const maxTop = Math.max(
    window.innerHeight - cardSize.height - VIEWPORT_MARGIN,
    VIEWPORT_MARGIN,
  );

  if (!targetRect) {
    return {
      left: Math.max((window.innerWidth - cardSize.width) / 2, VIEWPORT_MARGIN),
      top: Math.max((window.innerHeight - 180) / 2, VIEWPORT_MARGIN),
    };
  }

  const centeredLeft =
    targetRect.left + (targetRect.width - cardSize.width) / 2;
  const preferredLeft =
    centeredLeft <= VIEWPORT_MARGIN
      ? Math.min(Math.max(targetRect.left, VIEWPORT_MARGIN), maxLeft)
      : Math.min(Math.max(centeredLeft, VIEWPORT_MARGIN), maxLeft);
  const belowTop = targetRect.top + targetRect.height + CARD_GAP;
  const aboveTop = targetRect.top - cardSize.height - CARD_GAP;

  if (belowTop <= maxTop) {
    return { left: Math.max(preferredLeft, VIEWPORT_MARGIN), top: belowTop };
  }

  if (aboveTop >= VIEWPORT_MARGIN) {
    return { left: Math.max(preferredLeft, VIEWPORT_MARGIN), top: aboveTop };
  }

  const fitsRight =
    targetRect.left + targetRect.width + CARD_GAP + cardSize.width <=
    window.innerWidth - VIEWPORT_MARGIN;
  if (fitsRight) {
    return {
      left: targetRect.left + targetRect.width + CARD_GAP,
      top: Math.min(Math.max(targetRect.top, VIEWPORT_MARGIN), maxTop),
    };
  }

  const fitsLeft =
    targetRect.left - CARD_GAP - cardSize.width >= VIEWPORT_MARGIN;
  if (fitsLeft) {
    return {
      left: targetRect.left - CARD_GAP - cardSize.width,
      top: Math.min(Math.max(targetRect.top, VIEWPORT_MARGIN), maxTop),
    };
  }

  return {
    left: Math.max(preferredLeft, VIEWPORT_MARGIN),
    top: Math.min(Math.max(belowTop, VIEWPORT_MARGIN), maxTop),
  };
}

export function OnboardingOverlay({
  open,
  advanceAriaLabel,
  title,
  description,
  stepIndex,
  totalSteps,
  continueLabel,
  actionLabel,
  actionHref,
  targetRect,
  highlightPadding = PADDING,
  onAdvance,
}: OnboardingOverlayProps) {
  const cardRef = React.useRef<HTMLDivElement | null>(null);
  const [cardSize, setCardSize] = React.useState({
    width: DEFAULT_CARD_WIDTH,
    height: DEFAULT_CARD_HEIGHT,
  });

  React.useLayoutEffect(() => {
    if (!open || !cardRef.current) {
      return;
    }

    const nextSize = {
      width: cardRef.current.offsetWidth || DEFAULT_CARD_WIDTH,
      height: cardRef.current.offsetHeight || DEFAULT_CARD_HEIGHT,
    };

    setCardSize(current =>
      current.width === nextSize.width && current.height === nextSize.height
        ? current
        : nextSize,
    );
  }, [description, open, title, totalSteps]);

  if (!open) {
    return null;
  }

  const rect = targetRect
    ? {
        top: Math.max(targetRect.top - highlightPadding, 8),
        left: Math.max(targetRect.left - highlightPadding, 8),
        width: targetRect.width + highlightPadding * 2,
        height: targetRect.height + highlightPadding * 2,
      }
    : null;
  const cardStyle = buildCardPosition(rect, cardSize);
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 0;
  const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 0;

  return (
    <div className='fixed inset-0 z-[120]'>
      {rect ? (
        <>
          <button
            type='button'
            aria-label={advanceAriaLabel}
            onClick={onAdvance}
            className='absolute inset-0'
          />
          <svg
            className='pointer-events-none absolute inset-0 h-full w-full'
            aria-hidden='true'
            viewBox={`0 0 ${viewportWidth} ${viewportHeight}`}
            preserveAspectRatio='none'
          >
            <path
              fill={OVERLAY_BG}
              fillRule='evenodd'
              d={[
                `M0 0H${viewportWidth}V${viewportHeight}H0V0Z`,
                `M${rect.left + HIGHLIGHT_RADIUS} ${rect.top}`,
                `H${rect.left + rect.width - HIGHLIGHT_RADIUS}`,
                `A${HIGHLIGHT_RADIUS} ${HIGHLIGHT_RADIUS} 0 0 1 ${rect.left + rect.width} ${rect.top + HIGHLIGHT_RADIUS}`,
                `V${rect.top + rect.height - HIGHLIGHT_RADIUS}`,
                `A${HIGHLIGHT_RADIUS} ${HIGHLIGHT_RADIUS} 0 0 1 ${rect.left + rect.width - HIGHLIGHT_RADIUS} ${rect.top + rect.height}`,
                `H${rect.left + HIGHLIGHT_RADIUS}`,
                `A${HIGHLIGHT_RADIUS} ${HIGHLIGHT_RADIUS} 0 0 1 ${rect.left} ${rect.top + rect.height - HIGHLIGHT_RADIUS}`,
                `V${rect.top + HIGHLIGHT_RADIUS}`,
                `A${HIGHLIGHT_RADIUS} ${HIGHLIGHT_RADIUS} 0 0 1 ${rect.left + HIGHLIGHT_RADIUS} ${rect.top}`,
                'Z',
              ].join(' ')}
            />
          </svg>
          <div
            className='pointer-events-none absolute border border-white/70 shadow-[0_0_0_9999px_rgba(0,0,0,0)]'
            style={{
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
              borderRadius: `${HIGHLIGHT_RADIUS}px`,
              boxShadow:
                '0 0 0 1px rgba(255,255,255,0.55), 0 10px 32px rgba(255,255,255,0.10), 0 0 0 8px rgba(255,255,255,0.05)',
            }}
          />
        </>
      ) : (
        <button
          type='button'
          aria-label={advanceAriaLabel}
          onClick={onAdvance}
          className='absolute inset-0'
          style={{ backgroundColor: OVERLAY_BG }}
        />
      )}
      <div
        ref={cardRef}
        className='pointer-events-auto absolute'
        style={cardStyle}
        onClick={onAdvance}
      >
        <OnboardingCard
          title={title}
          description={description}
          stepIndex={stepIndex}
          totalSteps={totalSteps}
          continueLabel={continueLabel}
          actionLabel={actionLabel}
          actionHref={actionHref}
        />
      </div>
    </div>
  );
}
