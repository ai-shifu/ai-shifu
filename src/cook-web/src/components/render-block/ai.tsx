import { useState } from "react";
import { ALL_PLUGINS } from '@/components/md-editor'
// import { MDXEditor } from '@mdxeditor/editor';
import MDXEditor from '@/components/md-editor/ForwardRefEditor';

// import { Textarea } from "../ui/textarea";
// import { Textarea } from "../ui/textarea";
// import MarkdownEditor from '@/components/markdown-editor'


interface AIBlockProps {
    prompt: string;
    profiles: string[];
    model: string;
    temprature: string;
    other_conf: string;
}

interface AIBlock {
    properties: AIBlockProps;
    onChange: (properties: AIBlockProps) => void;
}

export default function AI(props: AIBlock) {
    const [isEdit, setIsEdit] = useState(true)
    if (isEdit) {
        return (
            <div className="bg-[#F5F5F4] rounded-md">
                <MDXEditor
                    className="h-60 overflow-auto"
                    markdown={props.properties.prompt}
                    onChange={(value) => {
                        props.onChange({ ...props.properties, prompt: value })
                    }}
                    plugins={ALL_PLUGINS}
                />
                {/* <MarkdownEditor initValue={props.properties.prompt} onChange={(value) => {
                        props.onChange({ ...props.properties, prompt: value })
                    }}>

                    </MarkdownEditor> */}
                {/* <Textarea value={props.properties.prompt} >

                    </Textarea> */}
            </div >
        )
    }
    return (
        <div onDoubleClick={() => setIsEdit(true)}>
            {props.properties.prompt}
        </div>

    )
}
