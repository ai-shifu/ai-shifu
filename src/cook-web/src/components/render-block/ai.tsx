
// import { MDXEditor } from '@mdxeditor/editor';
// import MDXEditor from '@/components/md-editor';
// import Markdown from '@/components/markdown'
import TextEditor from '@/components/text-editor';
// import { Textarea } from "../ui/textarea";
// import { Textarea } from "../ui/textarea";
// import MarkdownEditor from '@/components/markdown-editor'


interface AIBlockProps {
    prompt: string;
    profiles: string[];
    model: string;
    temprature: string;
    other_conf: string;
    content?: string; // Added optional content property
}

interface AIBlock {
    isEdit: boolean;
    properties: AIBlockProps;
    onChange: (properties: AIBlockProps) => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function AI(props: AIBlock) {

    if (props.properties.content) {
        props.properties.prompt = props.properties.content;
        delete props.properties.content;
    }

    return (
        <TextEditor
            content={props.properties.prompt}
            profiles={props.properties.profiles}
            isEdit={props.isEdit}
            onChange={(value, isEdit) => {
                props.onChange({ ...props.properties, prompt: value });
                if (props.onEditChange) {
                    props.onEditChange(isEdit);
                }
            }}
        />
    )
}
