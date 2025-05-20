"use client"
import { AuthProvider } from '@/store'
import React from 'react'
import ShifuEdit from '../shifu-edit'

export default function ShifuRoot({ id }: { id: string }) {

    return (
        <AuthProvider >
            <ShifuEdit id={id} />
        </AuthProvider>
    )
}
