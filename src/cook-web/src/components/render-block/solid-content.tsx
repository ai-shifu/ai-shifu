// import { MDXEditor } from '@mdxeditor/editor';
import MDXEditor from '@/components/md-editor/ForwardRefEditor';

import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm'

import { ALL_PLUGINS } from '@/components/md-editor';
// import { Textarea } from '../ui/textarea';
// import MarkdownEditor from '@/components/markdown-editor'

interface SolideContnetProps {
    content: string;
    profiles: string[];
}

interface SolideContnet {

    isEdit: boolean;
    properties: SolideContnetProps;
    onChange: (properties: SolideContnetProps) => void;
}

export default function SolidContent(props: SolideContnet) {

    const { isEdit } = props;
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

        <Markdown remarkPlugins={[remarkGfm]}>
            {props.properties.content}
        </Markdown>

    )
}
