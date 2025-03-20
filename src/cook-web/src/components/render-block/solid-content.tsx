// import { MDXEditor } from '@mdxeditor/editor';
import MDXEditor from '@/components/md-editor/ForwardRefEditor';

import { useState } from 'react';
import { ALL_PLUGINS } from '@/components/md-editor';
// import { Textarea } from '../ui/textarea';
// import MarkdownEditor from '@/components/markdown-editor'

interface SolideContnetProps {
    content: string;
    profiles: string[];
}

interface SolideContnet {
    properties: SolideContnetProps;
    onChange: (properties: SolideContnetProps) => void;
}

export default function SolidContent(props: SolideContnet) {
    const [isEdit, setIsEdit] = useState(true)
    if (isEdit) {
        return (
            <div className="bg-[#F5F5F4] rounded-md">
                <MDXEditor
                    className="h-60 overflow-auto"
                    markdown={props.properties.content}
                    onChange={(value) => {
                        props.onChange({ ...props.properties, content: value })
                    }}
                    plugins={ALL_PLUGINS}
                />

                {/* <Textarea value={props.properties.content} >

                    </Textarea> */}
            </div>

        )
    }
    return (
        <div onDoubleClick={() => setIsEdit(true)}>
            {props.properties.content}
        </div>

    )
}
