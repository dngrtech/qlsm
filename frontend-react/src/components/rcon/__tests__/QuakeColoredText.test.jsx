import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import QuakeColoredText, { parseQuakeColorSpans } from '../QuakeColoredText';

describe('QuakeColoredText', () => {
  it('strips only Quake color markers and returns palette-keyed text spans', () => {
    expect(parseQuakeColorSpans('plain ^1red ^2green^9 gray ^x literal')).toEqual([
      { text: 'plain ', color: null },
      { text: 'red ', color: '1' },
      { text: 'green', color: '2' },
      { text: ' gray ^x literal', color: '9' },
    ]);
  });

  it('renders multiline whitespace and untrusted markup as safe colored React text', () => {
    const { container } = render(<QuakeColoredText text={'^2  green\n^1<script>alert(1)</script>'} />);
    expect(screen.getByText(/green/)).toHaveStyle({ color: '#44ff44' });
    expect(screen.getByText(/<script>/)).toHaveStyle({ color: '#ff4444' });
    expect(container.querySelector('script')).toBeNull();
    expect(container).toHaveTextContent('green <script>alert(1)</script>');
    expect(container).not.toHaveTextContent('^2');
    expect(container.querySelector('pre')).toHaveClass('whitespace-pre-wrap');
  });

  it('retains an error tone when no explicit Quake color overrides it', () => {
    render(<QuakeColoredText text="failure" error />);
    expect(screen.getByText('failure')).toHaveClass('text-red-500');
  });
});
