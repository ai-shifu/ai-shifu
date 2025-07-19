import React from 'react';
import clsx from 'clsx';
import { Label } from '../Label';
import { HelpText } from '../HelpText';

export type FormItemProps = {
  label?: string | React.ReactNode;
  help?: string;
  required?: boolean;
  invalid?: boolean;
  hidden?: boolean;
  children?: React.ReactNode;
};

export const FormItem: React.FC<FormItemProps> = (props) => {
  const { label, help, required, invalid, hidden, children } = props;
  return (
    <div className={clsx('FormItem', { required, 'is-invalid': invalid })} hidden={hidden}>
      {/* @ts-expect-error EXPECT */}
      {label && <Label>{label}</Label>}
      {children}
      {/* @ts-expect-error EXPECT */}
      {help && <HelpText>{help}</HelpText>}
    </div>
  );
};
