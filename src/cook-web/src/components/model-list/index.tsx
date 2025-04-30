import { useScenario } from '@/store';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { cn } from '@/lib/utils';

export default function ModelList({
  value,
  className,
  onChange,
}: {
  value: string;
  className?: string;
  onChange: (value: string) => void;
}) {
  const { models } = useScenario();
  return (
    <Select onValueChange={onChange} defaultValue={value}>
      <SelectTrigger className={cn('w-full', className)}>
        <SelectValue placeholder="选择模型" />
      </SelectTrigger>
      <SelectContent>
        {models.map((item, i) => {
          return (
            <SelectItem key={i} value={item}>
              {item}
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
