import React, { useEffect, useState } from 'react';
import { Input } from '../ui/input';
import Button from '../button';
import { MinusIcon, PlusIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function InputNumber({
  value,
  min,
  max,
  step,
  onChange,
  className,
}: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  className?: string;
}) {
  const [number, setNumber] = useState(value);
  const onChangeValue = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.value || !e.target.value.match(/^[0-9]*[.]?[0-9]*$/)) {
      setNumber(0);
      return;
    }
    setNumber(parseFloat(e.target.value));
  };
  useEffect(() => {
    onChange(number);
  }, [number]);

  return (
    <div className={cn('flex items-center space-x-2', className)}>
      <Input
        type="text"
        value={value}
        onChange={onChangeValue}
        className="w-full"
      />
      <Button
        variant="outline"
        size="icon"
        className="h-8 w-8 shrink-0"
        disabled={number <= min}
        onClick={() => {
          if (number <= min) {
            setNumber(min);
            return;
          }
          setNumber(Number((number - step).toFixed(1)));
        }}
      >
        <MinusIcon className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        disabled={number >= max}
        size="icon"
        className="h-8 w-8 shrink-0"
        onClick={() => {
          if (number >= max) {
            setNumber(max);
            return;
          }
          setNumber(Number((number + step).toFixed(1)));
        }}
      >
        <PlusIcon className="h-4 w-4" />
      </Button>
    </div>
  );
}
