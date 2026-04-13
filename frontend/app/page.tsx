// "use client";
// import React, { useState } from 'react';
// import axios from 'axios';

// export default function Home() {
//   const [file, setFile] = useState(null);
//   const [text, setText] = useState('');
//   const [summary, setSummary] = useState('');
//   const [risky, setRisky] = useState([]);
//   const [loading, setLoading] = useState(false);

//   const handleFileChange = (e) => {
//     setFile(e.target.files[0]);
//     setSummary('');
//     setRisky([]);
//   };

//   const handleUpload = async () => {
//     if (!file) return;
//     const formData = new FormData();
//     formData.append('file', file);
//     setLoading(true);
//     try {
//       const response = await axios.post('http://localhost:5000/upload', formData, {
//         headers: { 'Content-Type': 'multipart/form-data' }
//       });
//       setText(response.data.text);
//     } catch (err) {
//       console.error('Error uploading file:', err);
//     }
//     setLoading(false);
//   };

//   const handleSummarize = async () => {
//     if (!text) return;
//     setLoading(true);
//     try {
//       const response = await axios.post('http://localhost:5000/summarize', { text });
//       setSummary(response.data.summary);
//     } catch (err) {
//       console.error('Error summarizing:', err);
//     }
//     setLoading(false);
//   };

//   const handleRisk = async () => {
//     if (!text) return;
//     setLoading(true);
//     try {
//       const response = await axios.post('http://localhost:5000/risk', { text });
//       setRisky(response.data.risky_clauses);
//     } catch (err) {
//       console.error('Error detecting risk:', err);
//     }
//     setLoading(false);
//   };

//   return (
//     <div className="min-h-screen p-8 bg-gray-100">
//       <h1 className="text-3xl font-bold mb-6">📄 Legal Document Analyzer</h1>

//       <input
//         type="file"
//         accept="application/pdf"
//         onChange={handleFileChange}
//         className="mb-4"
//       />
//       <button
//         onClick={handleUpload}
//         className="px-4 py-2 bg-blue-600 text-white rounded mb-4 hover:bg-blue-700"
//       >
//         Upload PDF
//       </button>

//       {text && (
//         <div className="flex gap-4 mb-6">
//           <button
//             onClick={handleSummarize}
//             className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
//           >
//             Summarize
//           </button>
//           <button
//             onClick={handleRisk}
//             className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
//           >
//             Detect Risky Clauses
//           </button>
//         </div>
//       )}

//       {loading && <p className="text-lg">⏳ Processing...</p>}

//       {summary && (
//         <div className="bg-white p-4 rounded shadow mb-6">
//           <h2 className="text-xl font-semibold mb-2">📝 Summary</h2>
//           <p>{summary}</p>
//         </div>
//       )}

//       {risky.length > 0 && (
//         <div className="bg-white p-4 rounded shadow">
//           <h2 className="text-xl font-semibold mb-2">⚠️ Risky Clauses</h2>
//           <ul className="list-disc list-inside">
//             {risky.map((risk, idx) => (
//               <li key={idx}>
//                 <strong>Pattern:</strong> {risk.pattern}
//                 <br />
//                 <strong>Matches:</strong> {risk.matches.join(', ')}
//               </li>
//             ))}
//           </ul>
//         </div>
//       )}
//     </div>
//   );
// }


"use client";

import React, { useState, useEffect } from "react";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001';

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [summaries, setSummaries] = useState<any[]>([]);
  const [showSidebar, setShowSidebar] = useState(false);
  const [uploadedFileSig, setUploadedFileSig] = useState<string | null>(null);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);

  useEffect(() => {
    fetchSummaries();
  }, []);

  const fetchSummaries = async () => {
    try {
      const response = await axios.get(`${API_BASE}/summaries`);
      setSummaries(response.data);
    } catch (error) {
      console.error("Error fetching summaries:", error);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    setResult("");
    setUploadedFileSig(null);
    setUploadedUrl(null);
    setUploadError(null);

    if (!selectedFile) return;

    // Upload immediately on select
    const sig = getFileSig(selectedFile);
    const s3FormData = new FormData();
    s3FormData.append("file", selectedFile);

    setUploading(true);
    try {
      const response = await axios.post(`${API_BASE}/upload-s3`, s3FormData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const url = response.data.file_url as string;
      setUploadedFileSig(sig);
      setUploadedUrl(url);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const serverMessage =
          error.response?.data?.error || error.response?.data?.message;
        setUploadError(serverMessage || "Error uploading file to S3.");
      } else {
        setUploadError(error instanceof Error ? error.message : "Error uploading file to S3.");
      }
    } finally {
      setUploading(false);
    }
  };

  const getFileSig = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;

  const ensureUploadedToS3 = async (): Promise<string> => {
    if (!file) {
      throw new Error("Please upload a file first.");
    }

    const sig = getFileSig(file);
    if (uploadedUrl && uploadedFileSig === sig) {
      return uploadedUrl;
    }

    const s3FormData = new FormData();
    s3FormData.append("file", file);

    setUploading(true);
    setUploadError(null);
    try {
      const response = await axios.post(`${API_BASE}/upload-s3`, s3FormData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const url = response.data.file_url as string;
      setUploadedFileSig(sig);
      setUploadedUrl(url);
      return url;
    } finally {
      setUploading(false);
    }
  };

  const handleUpload = async (type: "summarize" | "risk") => {
    if (!file) {
      setResult("Please upload a file first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setResult("");

    try {
      await ensureUploadedToS3();
      const endpoint = type === "summarize" ? "/summarize" : "/risk";
      const response = await axios.post(
        `${API_BASE}${endpoint}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );

      if (type === "summarize") {
        console.log("Summarize response:", response.data);
        setResult(`**Summary:**\n${response.data.summary}`);
        fetchSummaries(); // Refresh summaries
      } else if (type === "risk") {
        const risks = response.data.risky_clauses;
        // Format risky clauses as readable text
        const formatted = risks.map((clause: string) => `• ${clause}`).join('\n');
        setResult(`**Risk Clauses Detected:**\n\n${formatted}`);
      }
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const serverMessage =
          error.response?.data?.error || error.response?.data?.message;
        setResult(serverMessage ? `Error: ${serverMessage}` : "Error processing file.");
      } else {
        setResult(error instanceof Error ? `Error: ${error.message}` : "Error processing file.");
      }
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleQA = async () => {
    if (!file || !question.trim()) {
      setResult("Please upload a file and enter a question.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    formData.append("question", question);

    setLoading(true);
    setResult("");

    try {
      await ensureUploadedToS3();
      const response = await axios.post(
        `${API_BASE}/qa`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );
      setResult(response.data.answer);
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const serverMessage =
          error.response?.data?.error || error.response?.data?.message;
        setResult(serverMessage ? `Error: ${serverMessage}` : "Error answering question.");
      } else {
        setResult(error instanceof Error ? `Error: ${error.message}` : "Error answering question.");
      }
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-20px); }
        }
        .float-animation {
          animation: float 6s ease-in-out infinite;
        }
        .bg-pattern {
          background-image: 
            radial-gradient(circle at 20% 50%, rgba(59, 130, 246, 0.08) 0%, transparent 50%),
            radial-gradient(circle at 80% 80%, rgba(37, 99, 235, 0.06) 0%, transparent 50%);
          backdrop-filter: blur(50px);
        }
      `}</style>
      
      {/* Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 w-80 bg-white/95 backdrop-blur shadow-xl transform ${showSidebar ? 'translate-x-0' : '-translate-x-full'} transition-transform duration-300 ease-in-out`}>
        <div className="p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold text-gray-900">Saved Summaries</h2>
            <button
              onClick={() => setShowSidebar(false)}
              className="text-gray-500 hover:text-gray-700 transition"
            >
              ✕
            </button>
          </div>
          <div className="space-y-4 max-h-screen overflow-y-auto">
            {summaries.map((summary, index) => (
              <div key={index} className="border border-gray-200 rounded-lg p-3 bg-linear-to-br from-blue-50 to-white hover:shadow-md transition">
                <h3 className="font-semibold text-gray-900">{summary.filename}</h3>
                <p className="text-xs text-gray-500 mt-1">{new Date(summary.timestamp).toLocaleString()}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-blue-600 text-sm font-medium hover:text-blue-700">View summary</summary>
                  <p className="text-sm mt-2 text-gray-700">{summary.summary}</p>
                </details>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main content with gradient background */}
      <div className="min-h-screen relative bg-linear-to-br from-slate-900 via-blue-900 to-slate-900 overflow-hidden">
        {/* Animated background pattern */}
        <div className="absolute inset-0 bg-pattern opacity-40"></div>
        
        {/* Decorative floating elements */}
        <div className="absolute top-10 right-10 w-72 h-72 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 float-animation"></div>
        <div className="absolute -bottom-8 left-20 w-80 h-80 bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 float-animation" style={{ animationDelay: '2s' }}></div>
        <div className="absolute top-1/2 left-1/3 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 float-animation" style={{ animationDelay: '4s' }}></div>

        {/* Content container */}
        <div className="relative z-10 flex flex-col items-center justify-center min-h-screen p-6">
          <button
            onClick={() => setShowSidebar(!showSidebar)}
            className="fixed top-4 left-4 z-40 bg-white/90 backdrop-blur text-gray-900 px-4 py-2 rounded-lg shadow-lg hover:shadow-xl transition border border-white/20"
          >
            {showSidebar ? 'Hide' : 'Show'} Summaries
          </button>
          
          <div className="mb-8 text-center">
            <div className="inline-block">
              <h1 className="text-5xl sm:text-6xl font-extrabold mb-2 bg-linear-to-r from-blue-300 via-blue-100 to-indigo-300 bg-clip-text text-transparent">
                ⚖️ Legal Document Analyzer
              </h1>
            </div>
            <p className="text-blue-100 text-lg max-w-md mx-auto">
              Upload PDFs, analyze contracts, and detect legal risks with AI precision
            </p>
          </div>

          <div className="w-full max-w-2xl space-y-6">
            {/* Upload Card */}
            <div className="bg-white/10 backdrop-blur border border-white/20 rounded-2xl p-8 shadow-2xl hover:shadow-3xl transition">
              <div className="mb-6">
                <h2 className="text-2xl font-bold text-white mb-2">Upload & Analyze</h2>
                <p className="text-blue-100 text-sm">Upload a PDF to get started</p>
              </div>
              
              <label
                htmlFor="file-upload"
                className="cursor-pointer block border-2 border-dashed border-blue-300 bg-white/5 hover:bg-white/10 rounded-xl p-8 text-center transition duration-300"
              >
                {file ? (
                  <span className="text-sm font-medium text-green-300">
                    ✅ {file.name}
                  </span>
                ) : (
                  <div>
                    <div className="text-3xl mb-2">📄</div>
                    <span className="text-base font-medium text-white">
                      Click to upload a PDF
                    </span>
                    <p className="text-xs text-blue-200 mt-1">or drag and drop</p>
                  </div>
                )}
                {file && uploading && (
                  <div className="mt-3 text-xs text-yellow-300 animate-pulse">⏳ Uploading to S3…</div>
                )}
                {file && !uploading && uploadedUrl && uploadedFileSig === getFileSig(file) && (
                  <div className="mt-3 text-xs text-green-300">✓ Uploaded</div>
                )}
                {file && uploadError && (
                  <div className="mt-3 text-xs text-red-300">✘ Upload failed: {uploadError}</div>
                )}
                <input
                  id="file-upload"
                  type="file"
                  accept=".pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </label>

              {/* Action Buttons */}
              <div className="mt-6 grid grid-cols-2 gap-3">
                <button
                  onClick={() => handleUpload("summarize")}
                  disabled={loading || uploading}
                  className="bg-linear-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-semibold py-3 rounded-lg shadow-lg hover:shadow-xl transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  📋 Summarize
                </button>
                <button
                  onClick={() => handleUpload("risk")}
                  disabled={loading || uploading}
                  className="bg-linear-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white font-semibold py-3 rounded-lg shadow-lg hover:shadow-xl transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ⚠️ Risk Check
                </button>
              </div>
            </div>

            {/* Q&A Card */}
            <div className="bg-white/10 backdrop-blur border border-white/20 rounded-2xl p-8 shadow-2xl">
              <h2 className="text-xl font-bold text-white mb-4">Ask a Question</h2>
              <div className="space-y-3">
                <input
                  type="text"
                  placeholder="E.g., What is the contract termination date?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  className="w-full bg-white/10 border border-white/20 text-white placeholder-blue-200 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent transition"
                />
                <button
                  onClick={handleQA}
                  disabled={loading || uploading}
                  className="w-full bg-linear-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700 text-white font-semibold py-3 rounded-lg shadow-lg hover:shadow-xl transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  🔍 Ask
                </button>
              </div>
            </div>

            {/* Loading State */}
            {(loading || uploading) && (
              <div className="bg-white/10 backdrop-blur border border-white/20 rounded-2xl p-4 text-center">
                <p className="text-blue-200 text-sm flex items-center justify-center gap-2">
                  <span className="animate-spin">⏳</span> {uploading ? "Uploading…" : "Processing…"}
                </p>
              </div>
            )}

            {/* Result Card */}
            {result && (
              <div className="bg-white/95 backdrop-blur rounded-2xl p-6 shadow-2xl">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="font-bold text-lg text-gray-900">Result</h2>
                  <button
                    onClick={() => setResult("")}
                    className="text-xs bg-gray-200 hover:bg-gray-300 text-gray-900 px-3 py-1 rounded-lg transition"
                  >
                    Clear
                  </button>
                </div>
                <pre className="whitespace-pre-wrap text-sm text-gray-800 leading-relaxed max-h-96 overflow-y-auto">
                  {result.replace(/\\n/g, '\n')}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}