import CMEditor from '@/components/cm-editor';

interface SolideContnetProps {
  content: string;
  profiles: string[];
  prompt?: string;
  model?: string;
  temprature?: number;
  other_conf?: any;
}

interface SolideContnet {
  isEdit: boolean;
  properties: SolideContnetProps;
  onChange: (properties: SolideContnetProps) => void;
  onEditChange?: (isEdit: boolean) => void;
}

export default function SolidContent(props: SolideContnet) {
  if (props.properties.prompt) {
    props.properties.content = props.properties.prompt;
    delete props.properties.prompt;
    delete props.properties.model;
    delete props.properties.temprature;
    delete props.properties.other_conf;
  }

  return (
    <CMEditor
      content={props.properties.content}
      profiles={props.properties.profiles}
      isEdit={props.isEdit}
      onChange={(value, isEdit) => {
        props.onChange({ ...props.properties, content: value });
        if (props.onEditChange) {
          props.onEditChange(isEdit);
        }
      }}
    />
  );
}
