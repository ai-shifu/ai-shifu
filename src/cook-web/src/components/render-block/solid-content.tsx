import CMEditor from '@/components/cm-editor';


interface SolideContnetProps {
    content: string;
}

interface SolideContnet {

    isEdit: boolean;
    properties: SolideContnetProps;
    onChange: (properties: SolideContnetProps) => void;
    onBlur?: () => void;
    onEditChange?: (isEdit: boolean) => void;
}

export default function SolidContent(props: SolideContnet) {
    return (
        <CMEditor
            content={props.properties?.content ?? ''}
            isEdit={props.isEdit}
            onBlur={props.onBlur}
            onChange={(value, variables, isEdit) => {
                props.onChange({ ...props.properties, content: value })
                if (props.onEditChange) {
                    props.onEditChange(isEdit)
                }
            }}
        />

    )

}
