/**
 * Keep provider display strings whole: a rating may be a label like "1650 (Gold)".
 * A separate component keeps rank rendering out of the already large modal.
 */
export default function PlayerRankCell({ rank }) {
    return (
        <td className="px-3 py-2 font-mono text-theme-secondary text-right">
            {rank?.display ?? '—'}
        </td>
    );
}
