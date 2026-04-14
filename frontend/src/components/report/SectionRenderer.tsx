import ReactMarkdown from 'react-markdown';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell,
} from 'recharts';
import { CHART_PALETTE, PRINT_PALETTE, sentimentBarColor } from '@/lib/constants';

/* ------------------------------------------------------------------ */
/*  Markdown table parser                                              */
/* ------------------------------------------------------------------ */

interface ParsedTable {
  headers: string[];
  rows: string[][];
}

type ContentBlock =
  | { type: 'text'; value: string }
  | { type: 'table'; value: ParsedTable; headline?: string };

/** Extract markdown tables from content, returning interleaved text and table blocks.
 *  If the text block immediately before a table ends with a bold line, pull it out
 *  as the table/chart's takeaway headline. */
function splitContentBlocks(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
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
      // Try to extract a takeaway headline from the last line(s) of the text buffer
      let headline: string | undefined;
      if (textBuffer.length > 0) {
        const lastLine = textBuffer[textBuffer.length - 1].trim();
        // Match bold markdown line: **Some headline text**
        const boldMatch = lastLine.match(/^\*\*(.+)\*\*$/);
        if (boldMatch) {
          headline = boldMatch[1];
          textBuffer.pop();
        }
      }

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
        blocks.push({ type: 'table', value: { headers, rows }, headline });
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
/*  Annotation detection                                               */
/* ------------------------------------------------------------------ */

/** Check if a header name suggests sentiment data */
function isSentimentHeader(header: string): boolean {
  return /sentiment|score|rating|polarity/i.test(header);
}

/* ------------------------------------------------------------------ */
/*  Components                                                         */
/* ------------------------------------------------------------------ */

interface TableChartProps {
  table: ParsedTable;
  printMode?: boolean;
  headline?: string;
}

function TableChart({ table, printMode, headline: headlineProp }: TableChartProps) {
  const headline = headlineProp ?? generateTableHeadline(table);
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
    return (
      <div style={{ marginBottom: 24 }}>
        {headline && <ChartHeadline text={headline} printMode={printMode} />}
        <MarkdownTable table={table} printMode={printMode} />
      </div>
    );
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

  const colors = printMode ? PRINT_PALETTE : CHART_PALETTE;
  const textColor = printMode ? '#374151' : '#8B97A8';
  const gridColor = printMode ? '#e5e7eb' : '#1B2433';
  const bg = printMode ? '#f9fafb' : '#0D1117';

  // Check if any numeric columns represent sentiment — use semantic coloring
  const useSentimentColors = numericCols.length === 1 && isSentimentHeader(headers[numericCols[0]]);

  return (
    <div style={{ marginBottom: 24 }}>
      {headline && <ChartHeadline text={headline} printMode={printMode} />}

      {/* Chart */}
      <div
        style={{
          background: bg,
          border: `1px solid ${gridColor}`,
          borderRadius: 12,
          padding: '20px 16px 8px',
          marginBottom: 12,
          overflow: 'hidden',
          width: '100%',
          maxWidth: '100%',
        }}
      >
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: textColor }} axisLine={{ stroke: gridColor }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: textColor, fontFamily: "'JetBrains Mono', monospace" }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={printMode
                ? { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 12 }
                : { background: '#111820', border: '1px solid #1B2433', borderRadius: 8, fontSize: 12, color: '#E8ECF2' }
              }
            />
            {numericCols.length > 1 && <Legend wrapperStyle={{ fontSize: 11, color: textColor }} />}
            {numericCols.map((c, idx) => {
              if (useSentimentColors) {
                return (
                  <Bar
                    key={headers[c]}
                    dataKey={headers[c]}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={40}
                  >
                    {data.map((entry, di) => {
                      const val = entry[headers[c]];
                      const fill = typeof val === 'number' ? sentimentBarColor(val) : colors[idx % colors.length];
                      return <Cell key={di} fill={fill} />;
                    })}
                  </Bar>
                );
              }
              return (
                <Bar key={headers[c]} dataKey={headers[c]} fill={colors[idx % colors.length]} radius={[4, 4, 0, 0]} maxBarSize={40} />
              );
            })}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Data table below chart */}
      <MarkdownTable table={table} printMode={printMode} compact />
    </div>
  );
}

/** Generate a fallback headline from table data when the LLM didn't provide one */
function generateTableHeadline(table: ParsedTable): string | undefined {
  const { headers, rows } = table;
  if (rows.length === 0) return undefined;
  // Find the first numeric column
  let numCol = -1;
  for (let c = 0; c < headers.length; c++) {
    if (isNumericColumn(rows, c)) { numCol = c; break; }
  }
  if (numCol < 0) return undefined;
  // Find label column (first non-numeric)
  let labelCol = 0;
  for (let c = 0; c < headers.length; c++) {
    if (!isNumericColumn(rows, c)) { labelCol = c; break; }
  }
  // Find the row with the max absolute numeric value
  let maxVal = 0;
  let maxLabel = '';
  let minVal = Infinity;
  let minLabel = '';
  for (const row of rows) {
    const val = parseNumeric(row[numCol] ?? '');
    if (val == null) continue;
    if (Math.abs(val) > Math.abs(maxVal)) { maxVal = val; maxLabel = row[labelCol] ?? ''; }
    if (val < minVal) { minVal = val; minLabel = row[labelCol] ?? ''; }
  }
  if (!maxLabel) return undefined;
  if (rows.length >= 2 && minLabel !== maxLabel) {
    return `${maxLabel} leads at ${maxVal} while ${minLabel} trails at ${minVal} (${headers[numCol]}).`;
  }
  return `${maxLabel} recorded the highest ${headers[numCol]} at ${maxVal}.`;
}

/** Bold takeaway headline rendered above a chart */
function ChartHeadline({ text, printMode }: { text: string; printMode?: boolean }) {
  return (
    <p
      style={{
        fontWeight: 700,
        fontSize: 14,
        color: printMode ? '#111827' : '#E8ECF2',
        marginBottom: 8,
        lineHeight: 1.4,
      }}
    >
      {text}
    </p>
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
          return <TableChart key={i} table={block.value} printMode={printMode} headline={block.headline} />;
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
