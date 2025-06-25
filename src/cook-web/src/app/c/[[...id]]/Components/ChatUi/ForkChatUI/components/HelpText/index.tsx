import React from 'react';

export const HelpText: React.FC = (props) => {
  // @ts-expect-error EXPECT
  const { children, ...others } = props;
  return (
    <div className="HelpText" {...others}>
      {children}
    </div>
  );
};
