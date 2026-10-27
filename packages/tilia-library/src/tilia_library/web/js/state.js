// The files panel's state.
export const files = {
  rows: [],              // the server's rows, in the server's order
  sortKey: null,         // "name" | "state" | "timelines" | "path", or null for the server's order
  sortDir: 1,            // 1 ascending, -1 descending
  filter: "",
  expanded: new Set(),   // file ids whose timelines are shown
  details: new Map(),    // file id -> the answer of /api/files/<file_id>
};

// The query panel's state.
export const query = {
  tab: typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,  // one id per page load
  seq: 0,                // the newest request; an older answer is dropped
  pending: 0,            // requests that are out
  result: null,          // the last successful /api/ql answer
  restored: false,       // the remembered text has been put back
  expanded: new Set(),   // file ids whose cards show every match line
  contexts: new Map(),   // "<file id>|<timeline ids>" -> promise of the /api/ql-context answer
  contextsGeneration: null,  // the generation `contexts` was filled at
};

// The query panel's bulk edit (`query -> ACTION`).
export const edit = {
  live: null,            // the preview shown: {id, statement, plan: Map key -> entry, summary}, or null
  picks: new Map(),      // match key -> the user's own tick; kept when the text changes
};
