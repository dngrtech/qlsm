import { describe, expect, it } from 'vitest';

import runLimited from '../runLimited';

describe('runLimited', () => {
  it('never runs more than limit at once and keeps order', async () => {
    let running = 0;
    let peak = 0;
    const items = [1, 2, 3, 4, 5, 6, 7, 8, 9];
    const results = await runLimited(items, 4, async (n) => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((r) => setTimeout(r, 5 * (10 - n)));
      running -= 1;
      if (n === 5) throw new Error('boom');
      return n * 2;
    });

    expect(peak).toBe(4);
    expect(results.map((r) => r.item)).toEqual(items);
    expect(results[0]).toEqual({ item: 1, ok: true, value: 2 });
    expect(results[4].ok).toBe(false);
    expect(results[4].error.message).toBe('boom');
    expect(results[8]).toEqual({ item: 9, ok: true, value: 18 });
  });
});
