import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BulkActionsModal from '../BulkActionsModal';

const mocks = vi.hoisted(() => ({
  checkPluginUpdates: vi.fn(),
  applyPluginUpdates: vi.fn(),
  getDeferRestartsSetting: vi.fn(),
  getPresets: vi.fn(),
  getPresetKeepCvars: vi.fn(),
  previewPresetApply: vi.fn(),
  applyPresetToInstance: vi.fn(),
}));

vi.mock('../../../services/api', () => mocks);

const STALE = 'Preset or server changed since the preview. Preview again.';

const hosts = [
  {
    id: 1, name: 'alpha', status: 'ACTIVE', runtime: 'minqlx',
    instances: [
      { id: 11, name: 'a1', port: 27960, status: 'running' },
      { id: 12, name: 'a2', port: 27961, status: 'stopped' },
    ],
  },
  {
    id: 2, name: 'bravo', status: 'ACTIVE', runtime: 'minqlxtended',
    instances: [{ id: 21, name: 'b1', port: 27960, status: 'running' }],
  },
  {
    id: 3, name: 'charlie', status: 'ACTIVE', runtime: 'minqlxtended',
    instances: [{ id: 31, name: 'c1', port: 27960, status: 'running' }],
  },
];

const compatibility = {
  preset_runtime: 'minqlx',
  target_runtime: 'minqlxtended',
  auto_accepted: [],
  stripped: [{
    path: 'x.py', replacement: 'x.py', kind: 'replaceable', from_catalog: true,
    verdict: 'incompatible', reasons: ['uses an API the target lacks'],
  }],
};

const preview = (id, over = {}) => ({
  compatibility: {},
  needs_decision: false,
  keep_cvars: [],
  kept_cvars: [],
  diff: {
    files: [{ path: 'server.cfg', change: 'modified', diff: '--- a\n+++ b\n-set x 1\n+set x 2\n' }],
    plugins: null, hooks: null, admins: null, lan_rate: null, unchanged: false,
  },
  preview_hash: `h${id}`,
  target: {},
  ...over,
});

const renderTab = async () => {
  render(<BulkActionsModal isOpen onClose={() => {}} hosts={hosts} />);
  fireEvent.click(screen.getByRole('tab', { name: /apply preset/i }));
  const select = await screen.findByLabelText('Preset');
  await screen.findByRole('option', { name: /duel/ });
  fireEvent.change(select, { target: { value: '5' } });
};

const tick = (name) => fireEvent.click(screen.getByLabelText(`Server ${name}`));

// Waits for the keep_cvars of the ticked servers to load, then previews.
const preview_ = async () => {
  const button = screen.getByRole('button', { name: /^preview$/i });
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);
};

describe('BulkPresetApplyTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: false });
    mocks.getPresets.mockResolvedValue([{ id: 5, name: 'duel', runtime: 'minqlx' }]);
    mocks.getPresetKeepCvars.mockResolvedValue([]);
    mocks.previewPresetApply.mockImplementation(async (id) => preview(id));
    mocks.applyPresetToInstance.mockResolvedValue({ message: 'queued' });
  });

  // apply_compatibility's rule: a decision is needed until the operator sent
  // an accepted_replacements list (even []), and only for a stripped entry
  // that has a replacement.
  const needsDecision = (body, compat) => body.accepted_replacements == null
    && compat.stripped.some(e => e.replacement);

  it('the keep_cvars list is the union with sources', async () => {
    mocks.getPresetKeepCvars.mockImplementation(async (id) => (id === 11
      ? [{ cvar: 'sv_tags', sources: ['launch args'] }, { cvar: 'net_port', sources: ['launch args'] }]
      : [{ cvar: 'SV_TAGS', sources: ['plugin:tags.py'] }, { cvar: 'qlx_foo', sources: ['addon:x'] }]));
    await renderTab();
    tick('a1');
    tick('b1');

    const tags = await screen.findByLabelText('Keep sv_tags');
    expect(tags.checked).toBe(true);
    expect(screen.getByLabelText('Keep net_port').checked).toBe(true);
    expect(screen.getByLabelText('Keep qlx_foo').checked).toBe(true);
    expect(screen.queryByLabelText('Keep SV_TAGS')).toBeNull();
    expect(screen.getByText('launch args, plugin:tags.py')).toBeTruthy();
    expect(mocks.getPresetKeepCvars).toHaveBeenCalledWith(11, 5);
    expect(mocks.getPresetKeepCvars).toHaveBeenCalledWith(21, 5);
    expect(mocks.getPresetKeepCvars).toHaveBeenCalledTimes(2);
  });

  it('unticking a cvar sends keep_cvars without it', async () => {
    mocks.getPresetKeepCvars.mockImplementation(async (id) => (id === 11
      ? [{ cvar: 'sv_tags', sources: ['launch args'] }, { cvar: 'net_port', sources: ['launch args'] }]
      : [{ cvar: 'qlx_foo', sources: ['addon:x'] }]));
    await renderTab();
    tick('a1');
    tick('b1');
    fireEvent.click(await screen.findByLabelText('Keep net_port'));
    await screen.findByLabelText('Keep qlx_foo');
    fireEvent.change(screen.getByLabelText('Add cvar'), { target: { value: 'g_motd' } });
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }));
    // qlx_plugins is what a preset changes; it is never kept.
    fireEvent.change(screen.getByLabelText('Add cvar'), { target: { value: 'qlx_plugins' } });
    fireEvent.click(screen.getByRole('button', { name: /^add$/i }));

    await preview_();

    const body = { preset_id: 5, keep_cvars: ['sv_tags', 'qlx_foo', 'g_motd'] };
    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledTimes(2));
    expect(mocks.previewPresetApply).toHaveBeenCalledWith(11, body);
    expect(mocks.previewPresetApply).toHaveBeenCalledWith(21, body);
  });

  it('unchanged servers are not applied', async () => {
    mocks.previewPresetApply.mockImplementation(async (id) => (id === 11
      ? preview(id, { diff: { files: [], plugins: null, hooks: null, admins: null, lan_rate: null, unchanged: true } })
      : preview(id)));
    await renderTab();
    tick('a1');
    tick('b1');
    await preview_();

    const row = await screen.findByTestId('preset-row-11');
    await waitFor(() => expect(within(row).getByText('no changes')).toBeTruthy());
    await screen.findByText('server.cfg');
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    await waitFor(() => expect(screen.getByTestId('preset-result-21').textContent).toBe('queued'));
    expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(1);
    expect(mocks.applyPresetToInstance.mock.calls[0][0]).toBe(21);
  });

  it('compatibility is asked once per runtime', async () => {
    // a1 (minqlx) needs nothing; b1 and c1 (minqlxtended) need a decision
    // until x.py is accepted.
    mocks.previewPresetApply.mockImplementation(async (id, body) => {
      if (id === 11) return preview(id);
      const decided = body.accepted_replacements != null;
      return preview(id, {
        compatibility, needs_decision: needsDecision(body, compatibility), preview_hash: decided ? `d${id}` : `h${id}`,
      });
    });
    await renderTab();
    tick('a1');
    tick('b1');
    tick('c1');
    await preview_();

    expect(await screen.findByText(/won.t carry over/i)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));

    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledTimes(5));
    await waitFor(() => expect(screen.queryByText(/won.t carry over/i)).toBeNull());
    const keep = { preset_id: 5, keep_cvars: [], accepted_replacements: ['x.py'] };
    expect(mocks.previewPresetApply).toHaveBeenCalledWith(21, keep);
    expect(mocks.previewPresetApply).toHaveBeenCalledWith(31, keep);
    expect(mocks.previewPresetApply).not.toHaveBeenCalledWith(11, keep);

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(3));
    expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(21, { ...keep, restart: true, preview_hash: 'd21' });
    expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(11, {
      preset_id: 5, keep_cvars: [], restart: true, preview_hash: 'h11',
    });
  });

  it('cancelling the question for a runtime leaves its servers unapplied', async () => {
    mocks.previewPresetApply.mockImplementation(async (id) => (id === 21
      ? preview(id, { compatibility, needs_decision: true })
      : preview(id)));
    await renderTab();
    tick('a1');
    tick('b1');
    await preview_();

    await screen.findByText(/won.t carry over/i);
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    const row = await screen.findByTestId('preset-row-21');
    await waitFor(() => expect(within(row).getByText(/compatibility not confirmed/i)).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(screen.getByTestId('preset-result-11').textContent).toBe('queued'));
    expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(1);
    expect(mocks.previewPresetApply).toHaveBeenCalledTimes(2);
  });

  it('apply sends preview_hash and restart per server', async () => {
    await renderTab();
    tick('a1');
    tick('a2');
    await preview_();
    await waitFor(() => expect(screen.getAllByText('server.cfg').length).toBe(2));

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    await waitFor(() => expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(2));
    expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(11, {
      preset_id: 5, keep_cvars: [], restart: true, preview_hash: 'h11',
    });
    // A stopped server is not started by the apply.
    expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(12, {
      preset_id: 5, keep_cvars: [], restart: false, preview_hash: 'h12',
    });

    // A queued server is never sent twice.
    await waitFor(() => expect(screen.getByTestId('preset-result-12').textContent).toBe('queued'));
    expect(screen.getByRole('button', { name: /^apply$/i }).disabled).toBe(true);
  });

  it('restart follows the Defer restarts setting', async () => {
    mocks.getDeferRestartsSetting.mockResolvedValue({ enabled: true });
    await renderTab();
    await waitFor(() => expect(screen.getByLabelText(/restart servers to apply/i).checked).toBe(false));
    tick('a1');
    await preview_();
    await screen.findByText('server.cfg');

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(11, {
      preset_id: 5, keep_cvars: [], restart: false, preview_hash: 'h11',
    }));
  });

  it('a stripped plugin without a replacement is asked about, and confirming with nothing ticked applies', async () => {
    const noReplacement = {
      ...compatibility,
      stripped: [{ path: 'mine.py', replacement: null, kind: 'custom', verdict: 'incompatible', reasons: ['custom plugin'] }],
    };
    mocks.previewPresetApply.mockImplementation(async (id, body) => (id === 21
      ? preview(id, { compatibility: noReplacement, needs_decision: needsDecision(body, noReplacement) })
      : preview(id)));
    await renderTab();
    tick('a1');
    tick('b1');
    await preview_();

    expect(await screen.findByText(/won.t carry over/i)).toBeTruthy();
    expect(screen.getByText('mine.py')).toBeTruthy();
    const row = screen.getByTestId('preset-row-21');
    expect(within(row).getByText('needs decision')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));

    const decided = { preset_id: 5, keep_cvars: [], accepted_replacements: [] };
    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(21, decided));
    await waitFor(() => expect(within(screen.getByTestId('preset-row-21')).queryByText('needs decision')).toBeNull());

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(2));
    expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(21, { ...decided, restart: true, preview_hash: 'h21' });
  });

  it('unticking a replacement re-previews with [] and the server is applied', async () => {
    mocks.previewPresetApply.mockImplementation(async (id, body) => (id === 21
      ? preview(id, { compatibility, needs_decision: needsDecision(body, compatibility) })
      : preview(id)));
    await renderTab();
    tick('b1');
    await preview_();

    await screen.findByText(/won.t carry over/i);
    const replace = screen.getByLabelText(/version of x\.py instead/);
    expect(replace.checked).toBe(true);
    fireEvent.click(replace);
    fireEvent.click(screen.getByRole('button', { name: /load preset/i }));

    const decided = { preset_id: 5, keep_cvars: [], accepted_replacements: [] };
    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(21, decided));
    await screen.findByText('server.cfg');
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(mocks.applyPresetToInstance).toHaveBeenCalledWith(21, {
      ...decided, restart: true, preview_hash: 'h21',
    }));
  });

  it('a server whose cvars failed to load blocks Preview until Retry loads them', async () => {
    let fail = true;
    mocks.getPresetKeepCvars.mockImplementation(async (id) => {
      if (id === 21 && fail) throw { error: { message: 'SSH unreachable' } };
      return [{ cvar: `qlx_id${id}`, sources: ['addon:x'] }];
    });
    await renderTab();
    tick('a1');
    tick('b1');

    expect(await screen.findByText(/SSH unreachable/)).toBeTruthy();
    const button = screen.getByRole('button', { name: /^preview$/i });
    expect(button.disabled).toBe(true);

    fail = false;
    fireEvent.click(screen.getByRole('button', { name: /^retry$/i }));
    await screen.findByLabelText('Keep qlx_id21');
    await waitFor(() => expect(button.disabled).toBe(false));
    expect(screen.queryByText(/SSH unreachable/)).toBeNull();
    expect(mocks.getPresetKeepCvars.mock.calls.filter(([id]) => id === 21)).toHaveLength(2);
    expect(mocks.getPresetKeepCvars.mock.calls.filter(([id]) => id === 11)).toHaveLength(1);

    fireEvent.click(button);
    const body = { preset_id: 5, keep_cvars: ['qlx_id11', 'qlx_id21'] };
    await waitFor(() => expect(mocks.previewPresetApply).toHaveBeenCalledWith(21, body));
  });

  it('a stale row is not sent again by Apply', async () => {
    mocks.applyPresetToInstance.mockImplementation(async (id) => {
      if (id === 11) throw { error: { message: STALE }, status: 409 };
      return { message: 'queued' };
    });
    await renderTab();
    tick('a1');
    tick('b1');
    await preview_();
    await waitFor(() => expect(screen.getAllByText('server.cfg').length).toBe(2));

    const apply = screen.getByRole('button', { name: /^apply$/i });
    fireEvent.click(apply);
    await waitFor(() => expect(screen.getByTestId('preset-result-11').textContent).toBe('preview again'));
    await waitFor(() => expect(screen.getByTestId('preset-result-21').textContent).toBe('queued'));
    expect(apply.disabled).toBe(true);
    expect(mocks.applyPresetToInstance).toHaveBeenCalledTimes(2);
  });

  it('switching tabs keeps the previews and does not preview again', async () => {
    await renderTab();
    tick('a1');
    await preview_();
    await screen.findByText('server.cfg');

    fireEvent.click(screen.getByRole('tab', { name: /update plugins/i }));
    fireEvent.click(screen.getByRole('tab', { name: /apply preset/i }));

    expect(screen.getByText('server.cfg')).toBeTruthy();
    expect(screen.getByLabelText('Server a1').checked).toBe(true);
    expect(mocks.previewPresetApply).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /^apply$/i }).disabled).toBe(false);
  });

  it('a stale hash row says preview again', async () => {
    mocks.applyPresetToInstance.mockImplementation(async (id) => {
      if (id === 11) throw { error: { message: STALE }, status: 409 };
      if (id === 21) throw { error: { message: 'Another operation is running on instance "b1". Please wait for it to complete.' }, status: 409 };
      if (id === 31) throw { error: { message: 'Plugin compatibility needs a decision' }, status: 422 };
      return { message: 'queued' };
    });
    await renderTab();
    tick('a1');
    tick('b1');
    tick('c1');
    await preview_();
    await waitFor(() => expect(screen.getAllByText('server.cfg').length).toBe(3));

    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));

    await waitFor(() => expect(screen.getByTestId('preset-result-11').textContent).toBe('preview again'));
    expect(screen.getByTestId('preset-result-21').textContent).toBe('busy');
    expect(screen.getByTestId('preset-result-31').textContent).toBe('Plugin compatibility needs a decision');
  });
});
