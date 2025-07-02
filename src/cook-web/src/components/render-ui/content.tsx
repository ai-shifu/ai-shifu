
import CMEditor from '@/components/cm-editor';



interface ContentProps {
    content: string;
    llm_enabled: boolean;
    llm: string;
    llm_temperature: string;
}

interface Content {
    isEdit: boolean;
    properties: ContentProps;
    onChange: (properties: ContentProps) => void;
    onBlur?: () => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function Content(props: Content) {
    return (
        <CMEditor
            content={props.properties.content}
            isEdit={props.isEdit}
            onBlur={props.onBlur}
            onChange={(value, variables, isEdit) => {
                props.onChange({ ...props.properties, content: value });
                if (props.onEditChange) {
                    props.onEditChange(isEdit);
                }
            }}
        />
    )
}
