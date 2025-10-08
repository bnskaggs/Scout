"use client";

export type TableRendererProps = {
  rows: Array<Record<string, unknown>> | null | undefined;
};

function normalizeRows(rows: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return rows.map((row) => ({ ...row }));
}

export function TableRenderer({ rows }: TableRendererProps) {
  if (!rows || rows.length === 0) {
    return <p className="mt-4 text-sm text-gray-500">No rows returned.</p>;
  }

  const normalizedRows = normalizeRows(rows);
  let headers = Object.keys(normalizedRows[0] ?? {});

  if (headers.includes("change_pct_formatted")) {
    headers = headers.filter((header) => header !== "change_pct");
  }

  return (
    <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full divide-y divide-gray-200 text-left text-sm text-gray-700">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              {headers.map((header) => (
                <th key={header} className="px-4 py-3 font-semibold">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {normalizedRows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`} className="hover:bg-gray-50">
                {headers.map((header) => {
                  const value = row[header];
                  const displayValue = value === null || value === undefined ? "" : String(value);
                  return (
                    <td key={`${rowIndex}-${header}`} className="px-4 py-2">
                      {displayValue}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default TableRenderer;
