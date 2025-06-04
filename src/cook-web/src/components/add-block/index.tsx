"use client"
import React from 'react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../ui/dropdown-menu'
import { Plus } from 'lucide-react'
import { useContentTypes } from '../render-block'
import { BlockType } from '@/types/shifu'

export default function AddBlock({ onAdd }: { onAdd: (type: BlockType) => void }) {
    const contentTypes = useContentTypes()
    return (
        <DropdownMenu>
            <DropdownMenuTrigger>
                <div className='p-2 rounded-md bg-gray-100 hover:bg-gray-200 cursor-pointer flex items-center justify-center'>
                    <Plus className='h-4 w-4 shrink-0' />
                </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align='start' side='bottom' alignOffset={-5}>
                {
                    contentTypes.map((item) => {
                        return (
                            <DropdownMenuItem key={item.type} onClick={() => onAdd(item.type as BlockType)}>
                                <span className='text-sm'>{item.name}</span>
                            </DropdownMenuItem>
                        )
                    })
                }
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
