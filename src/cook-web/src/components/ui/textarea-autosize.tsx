"use client"

import * as React from "react"
import TextareaAutosizeLib from "react-textarea-autosize"

import { cn } from "@/lib/utils"

export interface TextareaAutosizeProps
  extends React.ComponentProps<typeof TextareaAutosizeLib> {
  className?: string
}

const TextareaAutosize = React.forwardRef<
  React.ElementRef<typeof TextareaAutosizeLib>,
  TextareaAutosizeProps
>(({ className, minRows = 3, maxRows, ...props }, ref) => {
  return (
    <TextareaAutosizeLib
      className={cn(
        "flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 resize-none",
        className
      )}
      minRows={minRows}
      maxRows={maxRows}
      ref={ref}
      {...props}
    />
  )
})
TextareaAutosize.displayName = "TextareaAutosize"

export { TextareaAutosize }
