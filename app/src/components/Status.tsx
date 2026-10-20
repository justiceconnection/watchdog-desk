import type { Status } from '../cards/types';

/** Where the verification reports are published. Unset: "Verified <date>" has no link and no repo path is shown. */
export const REPORT_BASE = (import.meta.env.VITE_REPORT_BASE as string | undefined) ?? '';
/** Every card carries a status. "Verified <date>" appears only when the sign-off is in the data; it links to the report only when REPORT_BASE is set. */
export function StatusBadge({ status, placeholder }: { status: Status; placeholder?: boolean }) {
  return (
    <span className="badges">
      {status.verified
        ? <span className="badge ok">Verified {status.verified}{REPORT_BASE && status.report && <> (<a href={`${REPORT_BASE}${status.report}`} target="_blank" rel="noreferrer">report</a>)</>}</span>
        : <span className="badge warn" title="The verifier has not signed off on this card yet.">Not yet verified</span>}
      {placeholder && <span className="badge ph" title="The numbers on this card are invented to show the layout.">Placeholder data</span>}
    </span>
  );
}
