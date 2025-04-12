
<<<<<<< HEAD
import TextEditor from '@/components/text-editor';
=======
import CMEditor from '@/components/cm-editor';
>>>>>>> upstream/quanquan/feat_new_editor


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

    return (
<<<<<<< HEAD
        <TextEditor
=======
        <CMEditor
>>>>>>> upstream/quanquan/feat_new_editor
            content={props.properties.prompt}
            profiles={props.properties.profiles}
            isEdit={props.isEdit}
            onChange={(value, isEdit) => {
                console.log(value)
                props.onChange({ ...props.properties, prompt: value });
                if (props.onEditChange) {
                    props.onEditChange(isEdit);
                }
            }}
        />
    )
}
