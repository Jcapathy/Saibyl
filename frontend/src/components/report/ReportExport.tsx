import { useState } from 'react';
import { Download } from 'lucide-react';
import api from '@/lib/api';

interface ReportExportProps {
  reportId: string;
  simulationName: string;
  sections?: { title: string; content: string }[];
}

export default function ReportExport({ reportId, simulationName, sections }: ReportExportProps) {
  const [exporting, setExporting] = useState<string | null>(null);

  const exportPDF = async () => {
    if (exporting) return;
    setExporting('pdf');
    try {
      const response = await api.post(`/reports/${reportId}/export`, { format: 'pdf' }, { responseType: 'blob' });
      downloadBlob(new Blob([response.data]), `${simulationName}-report.pdf`);
    } catch {
      console.warn('PDF export endpoint unavailable');
    } finally {
      setExporting(null);
    }
  };

  const exportCSV = () => {
    if (!sections || sections.length === 0) return;
    const rows = [['Section', 'Content']];
    for (const s of sections) {
      rows.push([s.title, s.content.replace(/"/g, '""')]);
    }
    const csv = rows.map((r) => r.map((c) => `"${c}"`).join(',')).join('\n');
    downloadBlob(new Blob([csv], { type: 'text/csv' }), `${simulationName}-report.csv`);
  };

  const exportJSON = () => {
    if (!sections) return;
    const json = JSON.stringify({ reportId, simulationName, sections }, null, 2);
    downloadBlob(new Blob([json], { type: 'application/json' }), `${simulationName}-report.json`);
  };

  return (
    <div className="flex gap-2">
      <button
        onClick={exportPDF}
        disabled={exporting === 'pdf'}
        className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors disabled:opacity-50"
      >
        <Download className="w-3.5 h-3.5" />
        PDF
      </button>
      <button
        onClick={exportCSV}
        className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors"
      >
        <Download className="w-3.5 h-3.5" />
        CSV
      </button>
      <button
        onClick={exportJSON}
        className="flex items-center gap-1.5 text-[12px] px-3 py-1.5 rounded-lg border border-[#1B2433] text-[#8B97A8] hover:text-[#E8ECF2] hover:border-[#5A6578] transition-colors"
      >
        <Download className="w-3.5 h-3.5" />
        JSON
      </button>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
