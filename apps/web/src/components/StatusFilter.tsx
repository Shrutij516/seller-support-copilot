"use client";

import { formatStatus } from "@/lib/format";

interface StatusFilterProps {
  id: string;
  label: string;
  value: string;
  statuses: readonly string[];
  onChange: (value: string) => void;
}

const ALL = "";

export function StatusFilter({ id, label, value, statuses, onChange }: StatusFilterProps) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
      >
        <option value={ALL}>All</option>
        {statuses.map((status) => (
          <option key={status} value={status}>
            {formatStatus(status)}
          </option>
        ))}
      </select>
    </div>
  );
}
