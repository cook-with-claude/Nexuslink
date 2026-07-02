// Single source of truth for call-type display labels.
//
// The mapping mirrors the FROZEN Phase 1 definitions (phase1_cdr/detection.py:
// CALL_OUT = 1, CALL_IN = 2, SMS_OUT = 11, SMS_IN = 22; the valid set is
// loader.VALID_CALL_TYPES). Do not edit one side without the other — a wrong
// pairing silently mislabels every row.
//
// Display-only: the numeric code stays the stored and filterable value
// everywhere. Filters submit the code; only what the user SEES is the label.

export const CALL_TYPE_LABELS = {
  1: "out call",
  2: "in call",
  11: "out SMS",
  22: "in SMS",
};

export function callTypeLabel(code) {
  const label = CALL_TYPE_LABELS[Number(code)];
  return label !== undefined ? label : String(code);
}

// [code, label] pairs for filter <select>s, ascending code order (1, 2, 11, 22).
export const CALL_TYPE_OPTIONS = Object.entries(CALL_TYPE_LABELS)
  .map(([code, label]) => [Number(code), label]);
