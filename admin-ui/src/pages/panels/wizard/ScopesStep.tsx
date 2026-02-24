import React from 'react';
import { Checkbox } from 'antd';
import { ALL_SCOPES } from './types';

export interface ScopesStepProps {
  data: string[];
  onChange: (scopes: string[]) => void;
}

const ScopesStep: React.FC<ScopesStepProps> = ({ data, onChange }) => {
  return (
    <Checkbox.Group
      value={data}
      onChange={(checkedValues) => onChange(checkedValues as string[])}
      style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
    >
      {ALL_SCOPES.map((scope) => (
        <Checkbox key={scope} value={scope}>
          {scope}
        </Checkbox>
      ))}
    </Checkbox.Group>
  );
};

export default ScopesStep;
