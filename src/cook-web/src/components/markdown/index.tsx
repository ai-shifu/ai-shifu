
import React from 'react'
import remarkGfm from 'remark-gfm'
import Markdown from 'react-markdown';

export default function Mark({ children }) {
    return (
        <div className={`markdown`}>
            <Markdown remarkPlugins={[remarkGfm]}>
                {children}
            </Markdown>
        </div>
    )
}
