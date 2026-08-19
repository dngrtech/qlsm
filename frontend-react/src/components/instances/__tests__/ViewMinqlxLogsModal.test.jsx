import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';

const mocks = vi.hoisted(() => ({
    fetchInstanceMinqlxLogs: vi.fn(),
    listInstanceMinqlxLogs: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
    fetchInstanceMinqlxLogs: mocks.fetchInstanceMinqlxLogs,
    listInstanceMinqlxLogs: mocks.listInstanceMinqlxLogs,
}));

// CodeMirrorEditor pulls in real @codemirror/view, unnecessary weight for
// tests that only exercise file-selection wiring.
vi.mock('../../CodeMirrorEditor', () => ({ default: () => <div data-testid="cm-editor" /> }));

// Not under test here — a plain stub is enough to keep the modal rendering.
vi.mock('../LogFilterControls', () => ({
    default: () => <div data-testid="filter-controls" />,
}));

vi.mock('@headlessui/react', async () => {
    const React = await import('react');
    const ListboxOnChangeContext = React.createContext(() => {});

    const Dialog = ({ open, children }) => (open ? <div role="dialog">{children}</div> : null);
    Dialog.Panel = ({ children }) => <div>{children}</div>;
    Dialog.Title = ({ children }) => <div>{children}</div>;
    const DialogBackdrop = () => <div />;
    const Transition = ({ children }) => <>{children}</>;

    const Listbox = ({ value, onChange, disabled, children }) => (
        <ListboxOnChangeContext.Provider value={onChange}>
            <div data-testid="listbox" data-value={value ?? ''} data-disabled={String(!!disabled)}>
                {children}
            </div>
        </ListboxOnChangeContext.Provider>
    );
    Listbox.Button = ({ children }) => <button type="button">{children}</button>;
    Listbox.Options = ({ children }) => <ul>{children}</ul>;
    // Named (capitalized) rather than assigned inline so eslint's rules-of-hooks
    // recognizes this as a component and allows the useContext call inside it.
    function ListboxOption({ value, children }) {
        const onChange = React.useContext(ListboxOnChangeContext);
        const content = typeof children === 'function' ? children({ selected: false }) : children;
        return (
            <li role="option" onClick={() => onChange(value)}>
                {content}
            </li>
        );
    }
    Listbox.Option = ListboxOption;

    return { Dialog, DialogBackdrop, Transition, Listbox };
});

import ViewMinqlxLogsModal from '../ViewMinqlxLogsModal';

describe('ViewMinqlxLogsModal runtime-aware file listing', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.fetchInstanceMinqlxLogs.mockResolvedValue({ logs: 'a log line' });
    });

    it('a minqlx instance lists and selects minqlx.log, unchanged from before', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({
            files: ['minqlx.log', 'minqlx.log.1', 'minqlx.log.2'],
        });
        const instance = { id: 1, name: 'mq-inst', port: 27960, host_runtime: 'minqlx' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(1));
        await waitFor(() =>
            expect(screen.getByTestId('listbox')).toHaveAttribute('data-value', 'minqlx.log')
        );

        // The very first request (fired in parallel with the file listing) must
        // already carry the correct filename for a minqlx host -- no request is
        // ever sent with an empty or wrong filename first.
        expect(mocks.fetchInstanceMinqlxLogs).toHaveBeenCalledWith(
            1,
            expect.objectContaining({ filename: 'minqlx.log' })
        );

        const options = screen.getAllByRole('option').map((el) => el.textContent);
        expect(options).toEqual(['minqlx.log', 'minqlx.log.1', 'minqlx.log.2']);
    });

    it('fetches log content exactly once on open, not once per pre- and post-seed render', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({
            files: ['minqlx.log', 'minqlx.log.1'],
        });
        const instance = { id: 1, name: 'mq-inst', port: 27960, host_runtime: 'minqlx' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(1));
        // Give the seed-then-settle render cycle a chance to fire a second time
        // if the dedup guard were missing.
        await new Promise((resolve) => setTimeout(resolve, 100));

        expect(mocks.fetchInstanceMinqlxLogs).toHaveBeenCalledTimes(1);
    });

    it('a minqlxtended instance lists and selects minqlxtended.log', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({
            files: ['minqlxtended.log', 'minqlxtended.log.1'],
        });
        const instance = { id: 2, name: 'mqx-inst', port: 27961, host_runtime: 'minqlxtended' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(2));
        await waitFor(() =>
            expect(screen.getByTestId('listbox')).toHaveAttribute('data-value', 'minqlxtended.log')
        );

        const options = screen.getAllByRole('option').map((el) => el.textContent);
        expect(options).toEqual(['minqlxtended.log', 'minqlxtended.log.1']);

        // No call was ever made carrying the minqlx filename this host's runtime
        // would reject -- checked over the full accumulated call history.
        const badCall = mocks.fetchInstanceMinqlxLogs.mock.calls.find(
            ([, opts]) => opts.filename === 'minqlx.log'
        );
        expect(badCall).toBeUndefined();
    });

    it('sorts rotated files after the live file by ascending numeric suffix', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({
            files: ['minqlxtended.log.3', 'minqlxtended.log', 'minqlxtended.log.1', 'minqlxtended.log.2'],
        });
        const instance = { id: 3, name: 'mqx-inst-2', port: 27962, host_runtime: 'minqlxtended' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(3));
        await waitFor(() => {
            const options = screen.getAllByRole('option').map((el) => el.textContent);
            expect(options).toEqual([
                'minqlxtended.log',
                'minqlxtended.log.1',
                'minqlxtended.log.2',
                'minqlxtended.log.3',
            ]);
        });
    });

    it('selecting a rotated file fetches it by the exact filename clicked', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({
            files: ['minqlxtended.log', 'minqlxtended.log.1'],
        });
        const instance = { id: 4, name: 'mqx-inst-3', port: 27963, host_runtime: 'minqlxtended' };
        const user = userEvent.setup();

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(2));
        mocks.fetchInstanceMinqlxLogs.mockClear();

        await user.click(screen.getByText('minqlxtended.log.1'));

        await waitFor(() => {
            expect(mocks.fetchInstanceMinqlxLogs).toHaveBeenCalledWith(
                4,
                expect.objectContaining({ filename: 'minqlxtended.log.1' })
            );
        });
    });

    it('does not fall back to a hardcoded minqlx.log when the file list is empty', async () => {
        mocks.listInstanceMinqlxLogs.mockResolvedValue({ files: [] });
        const instance = { id: 5, name: 'mqx-inst-4', port: 27964, host_runtime: 'minqlxtended' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(5));

        // Give any stray re-render a chance to settle, then confirm the option
        // list never contains the wrong runtime's hardcoded filename.
        await waitFor(() => {
            expect(screen.queryAllByRole('option').map((el) => el.textContent)).not.toContain(
                'minqlx.log'
            );
        });
    });

    it('does not fall back to a hardcoded minqlx.log when the file list call rejects', async () => {
        mocks.listInstanceMinqlxLogs.mockRejectedValueOnce(new Error('list failed'));
        const instance = { id: 6, name: 'mqx-inst-5', port: 27965, host_runtime: 'minqlxtended' };

        render(<ViewMinqlxLogsModal isOpen={true} onClose={() => {}} instance={instance} />);

        await waitFor(() => expect(mocks.listInstanceMinqlxLogs).toHaveBeenCalledWith(6));
        await waitFor(() => {
            expect(screen.queryAllByRole('option').map((el) => el.textContent)).not.toContain(
                'minqlx.log'
            );
        });

        // The initial content fetch (fired in parallel with the failed listing)
        // must still use the correct runtime default, not the minqlx literal.
        expect(mocks.fetchInstanceMinqlxLogs).toHaveBeenCalledWith(
            6,
            expect.objectContaining({ filename: 'minqlxtended.log' })
        );
    });
});
