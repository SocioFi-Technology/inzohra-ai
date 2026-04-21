"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export type DisciplineBarData = {
  discipline: string;
  matched: number;
  false_positives: number;
  missed: number;
  unaligned: number;
};

export function DisciplineBarChart({ data }: { data: DisciplineBarData[] }) {
  if (data.length === 0) return null;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 40 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="discipline"
          tick={{ fontSize: 10, fill: "#6b7280" }}
          angle={-30}
          textAnchor="end"
          interval={0}
        />
        <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} allowDecimals={false} />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 6 }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={((value: unknown, name: string) => [value, name.replace(/_/g, " ")]) as any}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          formatter={(v) => v.replace(/_/g, " ")}
        />
        <Bar dataKey="matched"         fill="#86efac" name="matched"         stackId="a" radius={[0, 0, 0, 0]} />
        <Bar dataKey="unaligned"       fill="#bfdbfe" name="unaligned"       stackId="a" />
        <Bar dataKey="false_positives" fill="#fca5a5" name="false_positives" stackId="a" />
        <Bar dataKey="missed"          fill="#fde68a" name="missed"          stackId="a" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
