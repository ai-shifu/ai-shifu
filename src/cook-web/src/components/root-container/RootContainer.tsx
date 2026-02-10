'use client';

import React from 'react';
import { useShallow } from 'zustand/react/shallow';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { useSystemStore, useUiLayoutStore } from '@/c-store';
import { cn } from '@/lib/utils';

type RootContainerProps = {
  children: React.ReactNode;
};

export default function RootContainer({ children }: RootContainerProps) {
  const learningMode = useSystemStore(state => state.learningMode);
  const { frameLayout, inMobile } = useUiLayoutStore(
    useShallow(state => ({
      frameLayout: state.frameLayout,
      inMobile: state.inMobile,
    })),
  );

  const isMobileLayout = frameLayout === FRAME_LAYOUT_MOBILE || inMobile;
  const shouldUseMinHeight = !(
    learningMode === 'listen' && isMobileLayout
  );

  return (
    <div
      id='root'
      className={cn(shouldUseMinHeight && 'min-h-screen')}
    >
      {children}
    </div>
  );
}
