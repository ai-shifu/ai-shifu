'use client';
import { UserProvider } from '@/store';
import React from 'react';
import ShifuEdit from '../shifu-edit';

type MainRootProps = {
  id: string;
  initialLessonId?: string;
  initialViewMode?: 'edit' | 'history';
};

export default function ShifuRoot({
  id,
  initialLessonId,
  initialViewMode,
}: MainRootProps) {
  return (
    <UserProvider>
      <ShifuEdit
        id={id}
        initialLessonId={initialLessonId}
        initialViewMode={initialViewMode}
      />
    </UserProvider>
  );
}
