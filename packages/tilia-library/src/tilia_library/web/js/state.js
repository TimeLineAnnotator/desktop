// The files panel's state.
export const files = {
  rows: [],              // the server's rows, in the server's order
  sortKey: null,         // "name" | "state" | "timelines" | "path", or null for the server's order
  sortDir: 1,            // 1 ascending, -1 descending
  filter: "",
  expanded: new Set(),   // file ids whose timelines are shown
  details: new Map(),    // file id -> the answer of /api/files/<file_id>
};
