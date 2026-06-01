import { useState } from 'react';
import { Send, Globe, Code, Clock, Activity, CheckCircle2, XCircle } from "lucide-react";

export default function TestingDashboard() {
  const [url, setUrl] = useState('https://jsonplaceholder.typicode.com/posts');
  const [method, setMethod] = useState('GET');
  const [reqBody, setReqBody] = useState('{\n  "title": "foo",\n  "body": "bar",\n  "userId": 1\n}');
  
  const [response, setResponse] = useState('// Hit Send to test the API...');
  const [status, setStatus] = useState(null); 
  const [time, setTime] = useState(null);
  const [loading, setLoading] = useState(false);

  // Tab state for the request area
  const [reqTab, setReqTab] = useState('body');

  const handleSend = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setStatus(null);
    setTime(null);
    setResponse('// Fetching...');

    const startTime = performance.now();
    try {
      const options = { method };
      
      // Only attach body for methods that support it
      if (['POST', 'PUT', 'PATCH'].includes(method)) {
        options.headers = { 'Content-Type': 'application/json' };
        try {
          // Validate JSON before sending
          JSON.parse(reqBody);
          options.body = reqBody;
        } catch {
          throw new Error("Invalid JSON in Request Body");
        }
      }

      const res = await fetch(url, options);
      const endTime = performance.now();

      setStatus({ code: res.status, text: res.statusText, ok: res.ok });
      setTime(Math.round(endTime - startTime));

      const contentType = res.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        const data = await res.json();
        setResponse(JSON.stringify(data, null, 2));
      } else {
        const text = await res.text();
        setResponse(text);
      }
    } catch (error) {
      setResponse(`Error: ${error.message}\n\nNote: Browsers block some requests due to CORS policies. Start with public APIs.`);
      setStatus({ code: 0, text: 'Failed', ok: false });
    }
    setLoading(false);
  };

  // UI Helpers
  const getMethodColor = (m) => {
    switch(m) {
      case 'GET': return 'text-green-400';
      case 'POST': return 'text-yellow-400';
      case 'PUT': return 'text-blue-400';
      case 'DELETE': return 'text-red-500';
      default: return 'text-white';
    }
  };

  const hasBody = ['POST', 'PUT', 'PATCH'].includes(method);

  return (
    <div className="h-full flex flex-col bg-[#121212] text-gray-300 font-sans">
      
      {/* Top Title Bar */}
      <div className="px-4 py-2 border-b border-borderDark flex items-center justify-between bg-[#181818] shrink-0">
        <div className="flex items-center gap-2">
          <Globe size={14} className="text-blue-400" />
          <span className="font-semibold text-xs tracking-wide">API WORKSPACE</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col p-4 gap-4 overflow-hidden">
        
        {/* URL / Request Bar */}
        <form onSubmit={handleSend} className="flex gap-2 shrink-0 h-9">
          <select 
            value={method} 
            onChange={(e) => setMethod(e.target.value)}
            className={`bg-[#1e1e1e] border border-borderDark rounded px-3 text-xs focus:outline-none focus:border-blue-500 font-bold w-24 cursor-pointer ${getMethodColor(method)}`}
          >
            <option className="text-green-400">GET</option>
            <option className="text-yellow-400">POST</option>
            <option className="text-blue-400">PUT</option>
            <option className="text-red-500">DELETE</option>
          </select>
          
          <input 
            type="text" 
            value={url} 
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Enter request URL"
            className="flex-1 bg-editorBg border border-borderDark rounded px-3 text-xs text-white focus:outline-none focus:border-blue-500 font-mono transition-colors"
          />
          
          <button 
            type="submit" 
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 text-white px-5 rounded text-xs font-semibold flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            {loading ? <Activity size={14} className="animate-spin" /> : <Send size={14} />}
            Send
          </button>
        </form>

        {/* Workspace Split: Request (Top) & Response (Bottom) */}
        <div className="flex-1 flex flex-col gap-4 overflow-hidden">
          
          {/* Request Config Area */}
          <div className="flex flex-col border border-borderDark rounded-lg overflow-hidden bg-[#1a1a1a] h-[40%] shrink-0">
            <div className="flex items-center bg-[#1e1e1e] border-b border-borderDark text-xs text-gray-400 px-2">
              <button 
                className={`px-3 py-1.5 border-b-2 transition-colors ${reqTab === 'body' ? 'border-blue-500 text-gray-200' : 'border-transparent hover:text-gray-300'}`}
                onClick={() => setReqTab('body')}
              >
                Body
              </button>
              <button 
                className={`px-3 py-1.5 border-b-2 transition-colors ${reqTab === 'headers' ? 'border-blue-500 text-gray-200' : 'border-transparent hover:text-gray-300'}`}
                onClick={() => setReqTab('headers')}
              >
                Headers
              </button>
            </div>
            
            <div className="flex-1 p-0 overflow-hidden relative">
              {reqTab === 'body' && (
                hasBody ? (
                  <textarea 
                    value={reqBody}
                    onChange={(e) => setReqBody(e.target.value)}
                    className="w-full h-full bg-transparent p-3 font-mono text-xs text-yellow-300 focus:outline-none resize-none"
                    spellCheck="false"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-xs text-gray-500 font-mono">
                    This request does not have a body
                  </div>
                )
              )}
              {reqTab === 'headers' && (
                <div className="w-full h-full flex items-center justify-center text-xs text-gray-500 font-mono">
                  Auto-generated headers hidden.
                </div>
              )}
            </div>
          </div>

          {/* Response Area */}
          <div className="flex-1 flex flex-col border border-borderDark rounded-lg overflow-hidden bg-editorBg min-h-0">
            {/* Response Status Bar */}
            <div className="bg-[#1e1e1e] p-2 border-b border-borderDark text-xs flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2 font-mono text-gray-400">
                <Code size={14} /> Response
              </div>
              
              {/* Telemetry */}
              {status && (
                <div className="flex items-center gap-4 font-mono">
                  <div className={`flex items-center gap-1 ${status.ok ? 'text-green-400' : 'text-red-400'}`}>
                    {status.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
                    Status: {status.code} {status.text}
                  </div>
                  <div className="flex items-center gap-1 text-blue-400">
                    <Clock size={12} />
                    Time: {time} ms
                  </div>
                </div>
              )}
            </div>
            
            {/* Response Body */}
            <div className="flex-1 p-3 overflow-auto">
              <pre className="text-xs text-green-400 font-mono whitespace-pre-wrap break-all">
                {response}
              </pre>
            </div>
          </div>
          
        </div>
      </div>
    </div>
  );
}