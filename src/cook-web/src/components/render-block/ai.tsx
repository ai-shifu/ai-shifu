
import CMEditor from '@/components/cm-editor';



interface AIBlockProps {
    prompt: string;
    profiles: string[];
    model: string;
    temperature: string;
    other_conf: string;
    content?: string; // Added optional content property
}

interface AIBlock {
    isEdit: boolean;
    properties: AIBlockProps;
    onChange: (properties: AIBlockProps) => void;
    onBlur?: () => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function AI(props: AIBlock) {
    return (
        <CMEditor
            content={props.properties.prompt}
            profiles={props.properties.profiles}
            isEdit={props.isEdit}
            onBlur={props.onBlur}
            onChange={(value, isEdit) => {
                props.onChange({ ...props.properties, prompt: value });
                if (props.onEditChange) {
                    props.onEditChange(isEdit);
                }
            }}
        />
    )
}
