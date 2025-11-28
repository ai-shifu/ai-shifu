import React, { useState, useRef, useEffect, useCallback } from 'react';
import { debounce } from 'lodash';
import { Input } from '../ui/Input';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { TITLE_MAX_LENGTH } from '@/c-constants/uiConstants';
interface InlineInputProps {
  isEdit?: boolean;
  value: string;
  onChange: (value: string) => void;
  className?: string;
  onFocus?: () => void;
  disabled?: boolean;
}

export const InlineInput: React.FC<InlineInputProps> = ({
  isEdit = false,
  value,
  onChange,
  className,
  disabled,
  onFocus,
}) => {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEdit) {
      setIsEditing(true);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 500);
    }
  }, [isEdit]);

  const handleDoubleClick = () => {
    if(disabled) return;
    setIsEditing(true);
    onFocus?.();
  };

  const handleBlur = () => {
    if (inputValue === '') {
      return;
    }
    setIsEditing(false);
    debouncedOnChange(inputValue);
  };

  const debouncedOnChange = useCallback(
    debounce((value: string) => {
      if (value === '') {
        return;
      }
      onChange(value || t('module.renderUi.inlineInput.unnamed'));
    }, 300),
    [onChange, t],
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
      debouncedOnChange(inputValue);
    }
  };

  useEffect(() => {
    setIsEditing(isEdit);
  }, [isEdit]);

  return (
    <div className={cn('inline-block w-full', className)}>
      {isEditing ? (
        <Input
          maxLength={TITLE_MAX_LENGTH}
          ref={inputRef}
          value={inputValue}
          onChange={handleChange}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          className='w-full h-6 border-none focus:outline-none focus:ring-0 px-2'
          onClick={e => e.stopPropagation()}
          onDrag={e => e.stopPropagation()}
          onDragCapture={e => e.stopPropagation()}
          onPointerDown={e => e.stopPropagation()}
        />
      ) : (
        <span
          title={value}
          className='w-full block whitespace-nowrap max-w-full overflow-hidden text-ellipsis'
          onDoubleClick={handleDoubleClick}
        >
          {value}
        </span>
      )}
    </div>
  );
};

export default InlineInput;
