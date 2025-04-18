import React from 'react'

interface ButtonViewProps {
    properties: {
        "button_name": string,
        "button_key": string,
    }
}

export default function ButtonView(props: ButtonViewProps) {
    const { properties } = props
    return (
        <div className='flex flex-row space-x-1 items-center'>
            <button
                className='px-4 py-2 bg-gray-100 text-gray-700 rounded-md cursor-default'
                disabled
            >
                {properties.button_name}
            </button>
        </div>
    )
}
