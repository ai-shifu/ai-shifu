'use client';
import { ShifuProvider } from '@/store';
import { UserProvider } from '@/store/userProvider';
import React from 'react';
import ShifuEdit from '../shifu-edit';

export default function ShifuRoot({ id }: { id: string }) {
  return (
    <UserProvider>
      <ShifuProvider>
        <ShifuEdit id={id} />
      </ShifuProvider>
    </UserProvider>
  );
}
