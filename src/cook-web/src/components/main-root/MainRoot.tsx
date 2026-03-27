'use client';
import { UserProvider } from '@/store';
import React from 'react';
import ShifuEdit from '../shifu-edit';

type MainRootProps = {
  id: string;
  initialLessonId?: string;
};

export default function ShifuRoot({ id, initialLessonId }: MainRootProps) {
  return (
    <UserProvider>
      <ShifuEdit id={id} initialLessonId={initialLessonId} />
    </UserProvider>
  );
}
