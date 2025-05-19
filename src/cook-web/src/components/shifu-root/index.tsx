"use client"
import { ShifuProvider, AuthProvider } from '@/store'
import React from 'react'
import ShifuEdit from '../shifu-edit'

export default function ShifuRoot({ id }: { id: string }) {

    return (
        <AuthProvider>
            <ShifuProvider>
                <ShifuEdit id={id} />
            </ShifuProvider>
        </AuthProvider>
    )
}
