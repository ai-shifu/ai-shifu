'use client';
import { ShifuProvider } from '@/store/useShifu';
import { UserProvider } from '@/store/userProvider';
import React from 'react';
import ShifuEdit from '../shifu-edit';

type ShifuRootProps = {
  id: string;
  initialLessonId?: string;
  initialViewMode?: 'edit' | 'history';
};

export default function ShifuRoot({
  id,
  initialLessonId,
  initialViewMode,
}: ShifuRootProps) {
  return (
    <UserProvider>
      <ShifuProvider>
        <ShifuEdit
          id={id}
          initialLessonId={initialLessonId}
          initialViewMode={initialViewMode}
        />
      </ShifuProvider>
    </UserProvider>
  );
}
