"use client"
import { AuthProvider } from '@/store'
import React from 'react'
import ScenarioEdit from '../scenario-edit'

export default function ScenarioRoot({ id }: { id: string }) {

    return (
        <AuthProvider >
            <ScenarioEdit id={id} />
        </AuthProvider>
    )
}
