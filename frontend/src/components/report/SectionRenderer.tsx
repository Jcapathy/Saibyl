import ReactMarkdown from 'react-markdown';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';

/* ------------------------------------------------------------------ */
/*  Markdown table parser                                              */
/* ------------------------------------------------------------------ */

interface ParsedTable {
  headers: string[];
  rows: string[][];
}

/** Extract markdown tables from content, returning interleaved text and table blocks */
function splitContentBlocks(content: string): Array<{ type: 'text'; value: string } | { type: 'table'; value: ParsedTable }> {
  const blocks: Array<{ type: 'text'; value: string } | { type: 'table'; value: ParsedTable }> = [];
  const lines = content.split('\n');
  let textBuffer: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Detect table: line has pipes and next line is a separator (---|---)
    if (
      line.includes('|') &&
      i + 1 < lines.length &&
      /^\s*\|?\s*[-:]+[-|:\s]+\s*\|?\s*$/.test(lines[i + 1])
    ) {
      // Flush text buffer
      if (textBuffer.length > 0) {
        blocks.push({ type: 'text', value: textBuffer.join('\n') });
        textBuffer = [];
      }

      // Parse header row
      const headers = line
        .split('|')
        .map(c => c.trim())
        .filter(c => c.length > 0);

      // Skip separator
      i += 2;

      // Parse data rows
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && !/^\s*\|?\s*[-:]+[-|:\s]+\s*\|?\s*$/.test(lines[i])) {
        const cells = lines[i]
          .split('|')
          .map(c => c.trim())
          .filter(c => c.length > 0);
        if (cells.length > 0) rows.push(cells);
        i++;
      }

      if (rows.length > 0) {
        blocks.push({ type: 'table', value: { headers, rows } });
      }
    } else {
      textBuffer.push(line);
      i++;
    }
  }

  if (textBuffer.length > 0) {
    blocks.push({ type: 'text', value: textBuffer.join('\n') });
  }

  return blocks;
}

/** Try to parse a cell value as a number (handles ratios like "2.1:1") */
function parseNumeric(cell: string): number | null {
  // Handle ratio format like "2.1:1" → take the first number
  const ratioMatch = cell.match(/^(\d+\.?\d*)\s*:\s*\d/);
  if (ratioMatch) return parseFloat(ratioMatch[1]);

  // Handle plain numbers
  const num = parseFloat(cell.replace(/[^0-9.\-+]/g, ''));
  if (!isNaN(num)) return num;

  return null;
}

/** Check if a column is mostly numeric */
function isNumericColumn(rows: string[][], colIndex: number): boolean {
  let numericCount = 0;
  for (const row of rows) {
    if (colIndex < row.length && parseNumeric(row[colIndex]) !== null) {
      numericCount++;
    }
  }
  return numericCount > rows.length * 0.5;
}

/* ------------------------------------------------------------------ */
/*  Chart colors                                                       */
/* ------------------------------------------------------------------ */

const CHART_COLORS = ['#5B5FEE', '#00D4FF', '#22C55E', '#F59E0B', '#EF4444', '#818CF8'];
const PRINT_COLORS = ['#4338ca', '#0891b2', '#16a34a', '#ca8a04', '#dc2626', '#6d28d9'];

/* ------------------------------------------------------------------ */
/*  Components                                                         */
/* ------------------------------------------------------------------ */

interface TableChartProps {
  table: ParsedTable;
  printMode?: boolean;
}

function TableChart({ table, printMode }: TableChartProps) {
  const { headers, rows } = table;

  // Find label column (first non-numeric) and numeric columns
  const numericCols: number[] = [];
  let labelCol = 0;

  for (let c = 0; c < headers.length; c++) {
    if (isNumericColumn(rows, c)) {
      numericCols.push(c);
    } else if (numericCols.length === 0) {
      labelCol = c;
    }
  }

  // If no numeric columns, render as plain table
  if (numericCols.length === 0) {
    return <MarkdownTable table={table} printMode={printMode} />;
  }

  // Build chart data
  const data = rows.map(row => {
    const entry: Record<string, string | number> = {
      name: row[labelCol] ?? '',
    };
    for (const c of numericCols) {
      const val = parseNumeric(row[c] ?? '');
      entry[headers[c]] = val ?? 0;
    }
    return entry;
  });

  const colors = printMode ? PRINT_COLORS : CHART_COLORS;
  const textColor = printMode ? '#374151' : '#8B97A8';
  const gridColor = printMode ? '#e5e7eb' : '#1B2433';
  const bg = printMode ? '#f9fafb' : '#0D1117';

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Chart */}
      <div
        style={{
          background: bg,
          border: `1px solid ${gridColor}`,
          borderRadius: 12,
          padding: '20px 16px 8px',
          marginBottom: 12,
        }}
      >
        {printMode ? (
          <BarChart width={680} height={280} data={data} margin={{ top: 8, right: 20, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: textColor }} axisLine={{ stroke: gridColor }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: textColor, fontFamily: "'JetBrains Mono', monospace" }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 12 }}
            />
            {numericCols.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
            {numericCols.map((c, idx) => (
              <Bar key={headers[c]} dataKey={headers[c]} fill={colors[idx % colors.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data} margin={{ top: 8, right: 20, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: textColor }} axisLine={{ stroke: gridColor }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: textColor, fontFamily: "'JetBrains Mono', monospace" }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#111820', border: '1px solid #1B2433', borderRadius: 8, fontSize: 12, color: '#E8ECF2' }}
              />
              {numericCols.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: textColor }} />}
              {numericCols.map((c, idx) => (
                <Bar key={headers[c]} dataKey={headers[c]} fill={colors[idx % colors.length]} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Data table below chart */}
      <MarkdownTable table={table} printMode={printMode} compact />
    </div>
  );
}

/** Styled HTML table for data that can't be charted, or as a companion to charts */
function MarkdownTable({ table, printMode, compact }: { table: ParsedTable; printMode?: boolean; compact?: boolean }) {
  const borderColor = printMode ? '#e5e7eb' : '#1B2433';
  const headerBg = printMode ? '#f3f4f6' : '#0D1117';
  const cellBg = printMode ? '#ffffff' : '#111820';
  const textColor = printMode ? '#374151' : '#8B97A8';
  const headerTextColor = printMode ? '#111827' : '#E8ECF2';
  const fontSize = compact ? 11 : 13;

  return (
    <div style={{ overflowX: 'auto', borderRadius: 8, border: `1px solid ${borderColor}` }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize }}>
        <thead>
          <tr>
            {table.headers.map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: 'left',
                  padding: compact ? '6px 12px' : '10px 14px',
                  background: headerBg,
                  color: headerTextColor,
                  fontWeight: 600,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: compact ? 10 : 11,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  borderBottom: `1px solid ${borderColor}`,
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    padding: compact ? '5px 12px' : '8px 14px',
                    background: cellBg,
                    color: textColor,
                    fontFamily: ci > 0 ? "'JetBrains Mono', monospace" : 'inherit',
                    borderBottom: ri < table.rows.length - 1 ? `1px solid ${borderColor}` : undefined,
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main export                                                        */
/* ------------------------------------------------------------------ */

interface SectionRendererProps {
  content: string;
  printMode?: boolean;
  className?: string;
}

export default function SectionRenderer({ content, printMode, className }: SectionRendererProps) {
  const blocks = splitContentBlocks(content);

  return (
    <div className={className}>
      {blocks.map((block, i) => {
        if (block.type === 'table') {
          return <TableChart key={i} table={block.value} printMode={printMode} />;
        }
        // Text block — render as markdown
        const trimmed = block.value.trim();
        if (!trimmed) return null;
        return (
          <div key={i} className={printMode ? undefined : 'prose prose-sm prose-invert max-w-none'}>
            <ReactMarkdown>{trimmed}</ReactMarkdown>
          </div>
        );
      })}
    </div>
  );
}
