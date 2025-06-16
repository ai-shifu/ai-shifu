import React from 'react'
import { memo } from 'react'
import _ from 'lodash'
interface ButtonViewProps {
    properties: {
        "button_name": string,
        "button_key": string,
    }
}
const ButtonViewPropsEqual = (prevProps: ButtonViewProps, nextProps: ButtonViewProps) => {
    if (! _.isEqual(prevProps.properties, nextProps.properties)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.button_name, nextProps.properties.button_name)) {
        return false
    }
    if (! _.isEqual(prevProps.properties.button_key, nextProps.properties.button_key)) {
        return false
    }
    return true
}
export default memo(function ButtonView(props: ButtonViewProps) {
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
},ButtonViewPropsEqual)
