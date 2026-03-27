'use client';
import { ShifuProvider } from '@/store';
import { UserProvider } from '@/store';
import React from 'react';
import ShifuEdit from '../shifu-edit';

type ShifuRootProps = {
  id: string;
  initialLessonId?: string;
};

export default function ShifuRoot({ id, initialLessonId }: ShifuRootProps) {
  return (
    <UserProvider>
      <ShifuProvider>
        <ShifuEdit id={id} initialLessonId={initialLessonId} />
      </ShifuProvider>
    </UserProvider>
  );
}
