import { render, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import CodeMirrorEditor from '../CodeMirrorEditor';
import { ThemeProvider } from '../../context/ThemeContext';

function renderEditor({ value, onChange }) {
  return (
    <ThemeProvider>
      <CodeMirrorEditor
        value={value}
        onChange={onChange}
        isActiveTab={true}
      />
    </ThemeProvider>
  );
}

describe('CodeMirrorEditor', () => {
  beforeAll(() => {
    const rect = {
      bottom: 0,
      height: 0,
      left: 0,
      right: 0,
      top: 0,
      width: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    };
    Range.prototype.getBoundingClientRect = () => rect;
    Range.prototype.getClientRects = () => [];
  });

  it('does not emit onChange for parent-driven value syncs', async () => {
    const onChange = vi.fn();
    const { rerender } = render(renderEditor({ value: '', onChange }));

    await waitFor(() => {
      expect(document.querySelector('.cm-editor')).toBeInTheDocument();
    });

    onChange.mockClear();
    rerender(renderEditor({ value: 'uploaded content', onChange }));

    await waitFor(() => {
      expect(document.querySelector('.cm-content')).toHaveTextContent('uploaded content');
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});
