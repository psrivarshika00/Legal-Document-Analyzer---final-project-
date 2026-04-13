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
  const [question, setQuestion] = useState("");
  const [summaries, setSummaries] = useState<any[]>([]);
  const [showSidebar, setShowSidebar] = useState(false);

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    setResult("");
  };

  const uploadCurrentFileToS3 = async (): Promise<string> => {
    if (!file) {
      throw new Error("Please upload a file first.");
    }

    const s3FormData = new FormData();
    s3FormData.append("file", file);

    const response = await axios.post(
      `${API_BASE}/upload-s3`,
      s3FormData,
      {
        headers: { "Content-Type": "multipart/form-data" },
      }
    );

    return response.data.file_url;
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
      await uploadCurrentFileToS3();
      const endpoint = type === "summarize" ? "/summarize" : "/risk";
      const response = await axios.post(
        `${API_BASE}${endpoint}`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );

      if (type === "summarize") {
        setResult(`**Fast Summary:**\n${response.data.fast_summary}\n\n**Accurate Summary:**\n${response.data.accurate_summary}`);
        fetchSummaries(); // Refresh summaries
      } else if (type === "risk") {
        const risks = response.data.risky_clauses;
        setResult(JSON.stringify(risks, null, 2));
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

  const handleUploadToS3 = async () => {
    if (!file) {
      setResult("Please upload a file first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setResult("");

    try {
      const response = await axios.post(
        `${API_BASE}/upload-s3`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );
      setResult(`Uploaded to S3:\n${response.data.file_url}`);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.data?.message) {
        setResult(`Error: ${error.response.data.message}`);
      } else {
        setResult("Error uploading file to S3.");
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
      await uploadCurrentFileToS3();
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
      {/* Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 w-80 bg-white shadow-lg transform ${showSidebar ? 'translate-x-0' : '-translate-x-full'} transition-transform duration-300 ease-in-out`}>
        <div className="p-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold">Saved Summaries</h2>
            <button
              onClick={() => setShowSidebar(false)}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>
          <div className="space-y-4 max-h-screen overflow-y-auto">
            {summaries.map((summary, index) => (
              <div key={index} className="border rounded p-3 bg-gray-50">
                <h3 className="font-semibold">{summary.filename}</h3>
                <p className="text-sm text-gray-600">{new Date(summary.timestamp).toLocaleString()}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-blue-600">Fast Summary</summary>
                  <p className="text-sm mt-1">{summary.fast_summary}</p>
                </details>
                <details className="mt-2">
                  <summary className="cursor-pointer text-blue-600">Accurate Summary</summary>
                  <p className="text-sm mt-1">{summary.accurate_summary}</p>
                </details>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="min-h-screen flex flex-col items-center justify-center bg-linear-to-b from-gray-100 to-white p-6">
        <button
          onClick={() => setShowSidebar(!showSidebar)}
          className="fixed top-4 left-4 z-40 bg-blue-600 text-white px-4 py-2 rounded shadow"
        >
          {showSidebar ? 'Hide' : 'Show'} Summaries
        </button>
      <h1 className="text-4xl font-bold mb-8 text-center text-blue-700">
        📄 Legal Document Analyzer
      </h1>

      <label
        htmlFor="file-upload"
        className="cursor-pointer w-full max-w-md border-2 border-dashed border-blue-400 bg-white rounded-lg p-6 text-center text-gray-600 hover:bg-blue-50 transition mb-6"
      >
        {file ? (
          <span className="text-sm font-medium text-gray-700">
            ✅ {file.name}
          </span>
        ) : (
          <span className="text-sm font-medium">
            Click here to upload a PDF file
          </span>
        )}
        <input
          id="file-upload"
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          className="hidden"
        />
      </label>

      <div className="flex space-x-4 mb-4">
        <button
          onClick={handleUploadToS3}
          className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-6 py-2 rounded shadow"
        >
          Upload to S3
        </button>
        <button
          onClick={() => handleUpload("summarize")}
          className="bg-blue-600 hover:bg-blue-700 text-white font-semibold px-6 py-2 rounded shadow"
        >
          Summarize
        </button>
        <button
          onClick={() => handleUpload("risk")}
          className="bg-red-600 hover:bg-red-700 text-white font-semibold px-6 py-2 rounded shadow"
        >
          Detect Risk Clauses
        </button>
      </div>

      <div className="flex flex-col w-full max-w-md space-y-3 mb-4">
        <input
          type="text"
          placeholder="Enter your legal question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="border border-gray-300 rounded px-4 py-2 w-full text-black"
        />
        <button
          onClick={handleQA}
          className="bg-purple-600 hover:bg-purple-700 text-white font-semibold px-6 py-2 rounded shadow"
        >
          Ask Question
        </button>
      </div>

      {loading && <p className="text-gray-500 text-sm">Processing...</p>}

      {result && (
        <div className="mt-6 w-full max-w-3xl bg-white p-4 rounded shadow border">
          <h2 className="font-semibold mb-2 text-lg text-gray-800">Result:</h2>
          <pre className="whitespace-pre-wrap text-sm text-gray-700">
            {result}
          </pre>
        </div>
      )}
    </div>
    </>
  );
}