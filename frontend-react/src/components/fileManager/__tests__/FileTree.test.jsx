import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import FileTree from '../FileTree';

describe('FileTree', () => {
  it('renders folders collapsed by default', () => {
    render(
      <FileTree
        files={[
          {
            name: 'extras',
            path: 'extras',
            type: 'folder',
            children: [
              { name: 'discord.py', path: 'extras/discord.py', type: 'file' },
            ],
          },
        ]}
        onSelectFile={vi.fn()}
        foldersEnabled
      />,
    );

    expect(screen.getByRole('button', { name: /extras/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /discord\.py/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /extras/i }));

    expect(screen.getByRole('button', { name: /discord\.py/i })).toBeInTheDocument();
  });

  it('sorts checked files first, then unchecked files alphabetically', () => {
    render(
      <FileTree
        files={[
          { name: 'zeta.py', path: 'zeta.py', type: 'file' },
          { name: 'bravo.py', path: 'bravo.py', type: 'file' },
          { name: 'alpha.py', path: 'alpha.py', type: 'file' },
          { name: 'charlie.py', path: 'charlie.py', type: 'file' },
        ]}
        onSelectFile={vi.fn()}
        checkable
        checkedFiles={new Set(['bravo.py', 'alpha.py'])}
      />,
    );

    const tree = screen.getByPlaceholderText(/search files/i).closest('.flex-col');
    const rows = within(tree).getAllByRole('button').map(button => button.textContent);

    expect(rows).toEqual(['alpha.py', 'bravo.py', 'charlie.py', 'zeta.py']);
  });

  it('keeps folders before checked and unchecked files in plugin trees', () => {
    render(
      <FileTree
        files={[
          { name: 'zeta.py', path: 'zeta.py', type: 'file' },
          { name: 'extras', path: 'extras', type: 'folder', children: [] },
          { name: 'alpha.py', path: 'alpha.py', type: 'file' },
          { name: 'bravo.py', path: 'bravo.py', type: 'file' },
        ]}
        onSelectFile={vi.fn()}
        checkable
        checkedFiles={new Set(['bravo.py', 'alpha.py'])}
        foldersEnabled
      />,
    );

    const tree = screen.getByPlaceholderText(/search files/i).closest('.flex-col');
    const rows = within(tree).getAllByRole('button').map(button => button.textContent);

    expect(rows).toEqual(['extras', 'alpha.py', 'bravo.py', 'zeta.py']);
  });

  it('does not move a file when the user checks it mid-session', () => {
    function TreeHarness() {
      const [checkedFiles, setCheckedFiles] = useState(new Set(['alpha.py']));
      const handleCheck = (path, checked) => {
        setCheckedFiles(prev => {
          const next = new Set(prev);
          if (checked) next.add(path);
          else next.delete(path);
          return next;
        });
      };

      return (
        <FileTree
          files={[
            { name: 'alpha.py', path: 'alpha.py', type: 'file' },
            { name: 'bravo.py', path: 'bravo.py', type: 'file' },
            { name: 'zeta.py', path: 'zeta.py', type: 'file' },
          ]}
          onSelectFile={vi.fn()}
          checkable
          checkedFiles={checkedFiles}
          onCheck={handleCheck}
        />
      );
    }

    render(<TreeHarness />);

    const tree = screen.getByPlaceholderText(/search files/i).closest('.flex-col');
    const rowsBefore = within(tree).getAllByRole('button').map(button => button.textContent);
    expect(rowsBefore).toEqual(['alpha.py', 'bravo.py', 'zeta.py']);

    fireEvent.click(within(tree).getAllByRole('checkbox')[2]);

    const rowsAfter = within(tree).getAllByRole('button').map(button => button.textContent);
    expect(rowsAfter).toEqual(['alpha.py', 'bravo.py', 'zeta.py']);
  });
});
