"use client"
import { ScenarioProvider } from '@/store'
import React from 'react'
import ScenarioEdit from '../scenario-edit'

export default function ScenarioRoot({ id }: { id: string }) {

    return (
        <ScenarioProvider >
            <ScenarioEdit id={id} />
        </ScenarioProvider>
    )
}
