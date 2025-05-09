"use client"
import { ScenarioProvider, AuthProvider } from '@/store'
import React from 'react'
import ScenarioEdit from '../scenario-edit'

export default function ScenarioRoot({ id }: { id: string }) {

    return (
        <AuthProvider>
            <ScenarioProvider>
                <ScenarioEdit id={id} />
            </ScenarioProvider>
        </AuthProvider>
    )
}
