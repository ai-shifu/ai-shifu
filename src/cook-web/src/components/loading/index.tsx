import { cn } from '@/lib/utils'
import React from 'react'

export default function Loading({ className }: { className?: string }) {
    return (
        <div className={cn(
            "animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-purple-600",
            className
        )} />
    )
}
