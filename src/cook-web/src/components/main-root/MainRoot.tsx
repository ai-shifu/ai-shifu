'use client';
import { UserProvider } from '@/store/userProvider';
import React from 'react';
import ShifuEdit from '../shifu-edit';

export default function ShifuRoot({ id }: { id: string }) {
  return (
    <UserProvider>
      <ShifuEdit id={id} />
    </UserProvider>
  );
}
