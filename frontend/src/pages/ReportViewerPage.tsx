import { useEffect, useState, FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import api from '@/lib/api';

interface Report {
  id: string;
  simulation_id: string;
  sections: { title: string; content: string }[];
  full_markdown: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export default function ReportViewerPage() {
  const { id: simId } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState(0);

  // Chat
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    api.get(`/reports/by-simulation/${simId}`)
      .then((res) => setReport(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [simId]);

  const sendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !report) return;
    const userMsg: ChatMessage = { role: 'user', content: chatInput };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput('');
    setChatLoading(true);
    try {
      const { data } = await api.post(`/reports/${report.id}/chat`, { message: chatInput });
      setChatMessages((prev) => [...prev, { role: 'assistant', content: data.response }]);
    } catch {
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Error getting response.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const exportReport = (format: string) => {
    if (!report) return;
    window.open(`${api.defaults.baseURL}/reports/${report.id}/export?format=${format}`, '_blank');
  };

  if (loading) return <div className="p-8 text-center text-saibyl-muted">Loading report...</div>;
  if (!report) return <div className="p-8 text-center text-red-500">Report not found.</div>;

  const sections = report.sections || [];

  return (
    <div className="h-screen flex bg-saibyl-void">
      {/* Left sidebar - sections */}
      <div className="w-56 bg-saibyl-deep border-r border-saibyl-border overflow-y-auto p-4">
        <h2 className="text-sm font-semibold text-saibyl-platinum mb-3">Sections</h2>
        <nav className="space-y-1">
          {sections.map((sec, i) => (
            <button
              key={i}
              onClick={() => setActiveSection(i)}
              className={`block w-full text-left text-sm px-3 py-2 rounded transition ${
                i === activeSection
                  ? 'bg-saibyl-surface text-saibyl-indigo font-medium'
                  : 'text-saibyl-muted hover:bg-saibyl-elevated'
              }`}
            >
              {sec.title}
            </button>
          ))}
        </nav>
      </div>

      {/* Main content - rendered markdown */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto bg-saibyl-deep rounded-2xl p-8 prose prose-sm prose-invert max-w-none border border-saibyl-border">
          {sections.length > 0 ? (
            <>
              <h1>{sections[activeSection].title}</h1>
              <ReactMarkdown>{sections[activeSection].content}</ReactMarkdown>
            </>
          ) : (
            <ReactMarkdown>{report.full_markdown || 'No content available.'}</ReactMarkdown>
          )}
        </div>
      </div>

      {/* Right panel - chat + export */}
      <div className="w-80 bg-saibyl-deep border-l border-saibyl-border flex flex-col">
        {/* Export buttons */}
        <div className="p-4 border-b border-saibyl-border">
          <h3 className="text-sm font-semibold text-saibyl-platinum mb-2">Export</h3>
          <div className="flex gap-2">
            <button onClick={() => exportReport('pdf')} className="text-xs bg-saibyl-indigo text-white px-3 py-1.5 rounded-lg hover:bg-[#4B4FDE]">
              PDF
            </button>
            <button onClick={() => exportReport('pptx')} className="text-xs bg-saibyl-indigo text-white px-3 py-1.5 rounded-lg hover:bg-[#4B4FDE]">
              PPTX
            </button>
            <button onClick={() => exportReport('json')} className="text-xs bg-saibyl-indigo text-white px-3 py-1.5 rounded-lg hover:bg-[#4B4FDE]">
              JSON
            </button>
          </div>
        </div>

        {/* Chat */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-saibyl-border">
            <h3 className="text-sm font-semibold text-saibyl-platinum">Ask about this report</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className={`text-sm p-2 rounded ${
                  msg.role === 'user'
                    ? 'bg-saibyl-surface text-saibyl-platinum ml-4'
                    : 'bg-saibyl-surface text-saibyl-platinum mr-4'
                }`}
              >
                {msg.content}
              </div>
            ))}
            {chatLoading && <div className="text-xs text-saibyl-muted">Thinking...</div>}
          </div>
          <form onSubmit={sendChat} className="p-3 border-t border-saibyl-border flex gap-2">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask a question..."
              className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-1.5 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
            />
            <button
              type="submit"
              disabled={chatLoading}
              className="bg-saibyl-indigo text-white px-3 py-1.5 rounded-lg text-sm hover:bg-[#4B4FDE] disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
