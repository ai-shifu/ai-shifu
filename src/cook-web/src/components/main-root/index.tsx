"use client"
import { UserProvider } from '@/c-store'
import React from 'react'
import ShifuEdit from '../shifu-edit'

export default function ShifuRoot({ id }: { id: string }) {

    return (
        <UserProvider>
            <ShifuEdit id={id} />
        </UserProvider>
    )
}
