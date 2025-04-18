import React, { useState, useRef, useEffect, useCallback } from 'react';
import { debounce } from 'lodash';
import { Input } from '../ui/input';
import { cn } from '@/lib/utils';

interface InlineInputProps {
  isEdit?: boolean;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  onFocus?: () => void;
}

export const InlineInput: React.FC<InlineInputProps> = ({ isEdit = false, value, onChange, className, onFocus }) => {
  const [isEditing, setIsEditing] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEdit) {

      setIsEditing(true);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 500)
    }
  }, [isEdit]);

  const handleDoubleClick = () => {
    setIsEditing(true);
    onFocus?.()
  };

  const handleBlur = () => {
    if (inputValue === "") {
      return;
    }
    setIsEditing(false);
    debouncedOnChange(inputValue);
  };

  const debouncedOnChange = useCallback(
    debounce((value: string) => {
      if (value === "") {
        return;
      }
      onChange(value || "未命名");
    }, 300),
    [onChange]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setInputValue(newValue);
  };

  useEffect(() => {
    return () => {
      debouncedOnChange.cancel();
    };
  }, [debouncedOnChange]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      setIsEditing(false);
      console.log('enter', inputValue)
      debouncedOnChange(inputValue);
    }
  };

  useEffect(() => {
    setIsEditing(isEdit);
  }, [isEdit])

  return (
    <div className={cn('inline-block w-full', className)}>
      {isEditing ? (
        <Input
          maxLength={20}
          ref={inputRef}
          value={inputValue}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          className="w-full h-6 border-none focus:outline-none focus:ring-0 px-2"
          onClick={(e) => e.stopPropagation()}
          onDrag={(e) => e.stopPropagation()}
          onDragCapture={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
        />
      ) : (
        <span title={value} className='w-full block whitespace-nowrap  max-w-52 2xl:max-w-72 overflow-hidden text-ellipsis' onDoubleClick={handleDoubleClick}>{value}</span>
      )}
    </div>
  );
};
