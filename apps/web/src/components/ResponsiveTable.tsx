"use client";

import Link from "next/link";
import type { ReactNode } from "react";

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
}

interface ResponsiveTableProps<T> {
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  rowHref?: (row: T) => string;
  emptyMessage: string;
}

/** A real <table> at md and up; the same data as a stack of cards below md. Both render
 * from the same `columns`/`rows`, so there's one source of truth for what each row shows.
 */
export function ResponsiveTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  rowHref,
  emptyMessage,
}: ResponsiveTableProps<T>) {
  if (rows.length === 0) {
    return <p className="text-slate-500 dark:text-slate-400">{emptyMessage}</p>;
  }

  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              {columns.map((col) => (
                <th key={col.header} scope="col" className="px-3 py-2 font-semibold">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)} className="border-b border-slate-100 dark:border-slate-900">
                {columns.map((col, i) => (
                  <td key={col.header} className="px-3 py-2">
                    {i === 0 && rowHref ? (
                      <Link href={rowHref(row)} className="hover:underline">
                        {col.cell(row)}
                      </Link>
                    ) : (
                      col.cell(row)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 md:hidden">
        {rows.map((row) => {
          const [first, ...rest] = columns;
          const card = (
            <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              {first && <p className="font-medium">{first.cell(row)}</p>}
              <dl className="mt-2 space-y-1 text-sm">
                {rest.map((col) => (
                  <div key={col.header} className="flex justify-between gap-3">
                    <dt className="text-slate-500 dark:text-slate-400">{col.header}</dt>
                    <dd>{col.cell(row)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
          return (
            <li key={rowKey(row)}>
              {rowHref ? (
                <Link href={rowHref(row)} className="block">
                  {card}
                </Link>
              ) : (
                card
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
