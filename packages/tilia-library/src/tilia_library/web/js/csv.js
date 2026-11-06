const SECONDS = /^(start|end|\$\d+\.start|\$\d+\.end)$/;

function cell(column, value) {
  if (value === null || value === undefined) return "";
  const s = typeof value === "number" && SECONDS.test(column) ? value.toFixed(3) : String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/**
 * The rows as CSV: the columns as header, LF line ends, no byte-order mark.
 * @param {string[]} columns
 * @param {Array<Record<string, any>>} rows  each keyed by column
 */
export function toCsv(columns, rows) {
  const lines = [columns.map(c => cell("", c)).join(",")];
  for (const row of rows) lines.push(columns.map(c => cell(c, row[c])).join(","));
  return lines.join("\n") + "\n";
}

/** Hand the text to the browser as a file. */
export function downloadCsv(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
