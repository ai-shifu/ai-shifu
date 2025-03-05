"use client"
import { ScenarioProvider } from '@/store'
import React from 'react'
import Header from '../header'
import ScenarioEdit from '../scenario-edit'

export default function ScenarioRoot({ id }: { id: string }) {

    return (
        <ScenarioProvider >
            <div className='sticky top-0'>
                <Header />
            </div>
            <ScenarioEdit id={id} />
        </ScenarioProvider>
    )
}
