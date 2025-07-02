import CMEditor from '@/components/cm-editor';


interface SolideContnetProps {
    variables: string[];
    prompt?: string;
    model?: string;
    temperature?: number;
    other_conf?: any;
}

interface SolideContnet {

    isEdit: boolean;
    properties: SolideContnetProps;
    onChange: (properties: SolideContnetProps) => void;
    onBlur?: () => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function SolidContent(props: SolideContnet) {
    console.log('SolidContent', props.properties)
    return (
        <CMEditor
            content={props.properties?.prompt ?? ''}
            isEdit={props.isEdit}
            onBlur={props.onBlur}
            onChange={(value, variables, isEdit) => {
                props.onChange({ ...props.properties, prompt: value, variables: variables })
                if (props.onEditChange) {
                    props.onEditChange(isEdit)
                }
            }}
        />

    )

}
