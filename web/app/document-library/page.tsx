"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getProjects,
  getDocuments,
  createProject,
  deleteDocument,
  getDocumentViewUrl,
  searchDocuments,
  getSearchFacets,
  type Project,
  type Document,
} from "@/lib/api";
import UploadModal from "@/components/UploadModal";
import DocumentChatModal from "@/components/DocumentChatModal";
import {
  FolderPlusIcon,
  ArrowUpTrayIcon,
  TrashIcon,
  EyeIcon,
  MagnifyingGlassIcon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  SparklesIcon,
  TagIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  ArrowDownTrayIcon,
  FolderIcon,
  CalendarIcon,
  ChevronRightIcon,
} from "@heroicons/react/24/outline";

export default function DocumentLibraryPage() {
  const queryClient = useQueryClient();
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectType, setNewProjectType] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [docTypeFilter, setDocTypeFilter] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [chatDoc, setChatDoc] = useState<Document | null>(null);
  const [showChat, setShowChat] = useState(false);

  const { data: projects } = useQuery({ queryKey: ["projects"], queryFn: getProjects });
  const { data: documents } = useQuery({
    queryKey: ["documents", selectedProject, categoryFilter, docTypeFilter],
    queryFn: () =>
      getDocuments({
        project_id: selectedProject || undefined,
        category: categoryFilter || undefined,
        doc_type: docTypeFilter || undefined,
      }),
  });

  const { data: facets } = useQuery({
    queryKey: ["facets", selectedProject],
    queryFn: () => getSearchFacets(selectedProject || undefined),
  });

  const { data: searchResults } = useQuery({
    queryKey: ["search", search, selectedProject, categoryFilter, docTypeFilter],
    queryFn: () =>
      searchDocuments(search, {
        project_id: selectedProject || undefined,
        category: categoryFilter || undefined,
        doc_type: docTypeFilter || undefined,
      }),
    enabled: search.length > 1,
  });

  const createProjectMutation = useMutation({
    mutationFn: () => createProject(newProjectName, undefined, newProjectType || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowNewProject(false);
      setNewProjectName("");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (selectedDoc) setSelectedDoc(null);
    },
  });

  const handleSelectDoc = async (doc: Document) => {
    setSelectedDoc(doc);
    try {
      const { url } = await getDocumentViewUrl(doc.id);
      setViewerUrl(url);
    } catch {
      setViewerUrl(null);
    }
  };

  const displayDocs = useMemo(() => {
    if (search.length > 1 && searchResults) {
      const ids = new Set(searchResults.map((r) => r.id));
      return (documents || []).filter((d) => ids.has(d.id));
    }
    return documents || [];
  }, [documents, search, searchResults]);

  const docTypeColor = (type: string | null) => {
    const colors: Record<string, string> = {
      budget: "bg-green-100 text-green-700",
      audit: "bg-blue-100 text-blue-700",
      financial_statement: "bg-purple-100 text-purple-700",
      minutes: "bg-yellow-100 text-yellow-700",
      agenda: "bg-orange-100 text-orange-700",
      ordinance: "bg-red-100 text-red-700",
      resolution: "bg-indigo-100 text-indigo-700",
      legal: "bg-pink-100 text-pink-700",
    };
    return colors[type || ""] || "bg-gray-100 text-gray-600";
  };

  return (
    <div className="flex h-full">
      {/* Left: Document list (scrollable) */}
      <div className={`${selectedDoc ? "w-[400px]" : "flex-1"} flex flex-col border-r bg-white transition-all`}>
        {/* Header */}
        <div className="px-4 py-3 border-b bg-gray-50">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-gray-900">Documents</h1>
            <div className="flex gap-2">
              <button
                onClick={() => setShowNewProject(true)}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200"
                title="New Project"
              >
                <FolderPlusIcon className="w-4 h-4" />
              </button>
              {selectedProject && (
                <button
                  onClick={() => setShowUpload(true)}
                  className="p-1.5 text-green-600 hover:text-green-700 rounded hover:bg-green-50"
                  title="Upload"
                >
                  <ArrowUpTrayIcon className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-2">
            <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search document content..."
              className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
            />
          </div>

          {/* Filters */}
          <div className="flex gap-2 text-xs">
            <select
              value={selectedProject || ""}
              onChange={(e) => setSelectedProject(e.target.value || null)}
              className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs"
            >
              <option value="">All Projects</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded text-xs"
            >
              <option value="">Category</option>
              <option value="town">Town</option>
              <option value="school">School</option>
            </select>
            <select
              value={docTypeFilter}
              onChange={(e) => setDocTypeFilter(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded text-xs"
            >
              <option value="">Type</option>
              {facets && Object.keys(facets.doc_types).map((k) => (
                <option key={k} value={k === "unclassified" ? "" : k}>{k}</option>
              ))}
            </select>
          </div>
          <div className="text-xs text-gray-400 mt-1">{displayDocs.length} documents</div>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto">
          {displayDocs.map((doc) => (
            <button
              key={doc.id}
              onClick={() => handleSelectDoc(doc)}
              className={`w-full text-left px-4 py-3 border-b hover:bg-gray-50 transition-colors ${
                selectedDoc?.id === doc.id ? "bg-green-50 border-l-4 border-l-green-500" : ""
              }`}
            >
              <div className="flex items-start gap-2">
                <DocumentTextIcon className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
                  <div className="flex items-center gap-1.5 mt-1">
                    {doc.doc_type && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${docTypeColor(doc.doc_type)}`}>
                        {doc.doc_type}
                      </span>
                    )}
                    {doc.category && (
                      <span className="text-[10px] text-gray-400 capitalize">{doc.category}</span>
                    )}
                    {doc.fiscal_year && (
                      <span className="text-[10px] text-gray-400">FY{doc.fiscal_year}</span>
                    )}
                  </div>
                  {doc.notes && (
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{doc.notes}</p>
                  )}
                </div>
                <ChevronRightIcon className="w-3 h-3 text-gray-300 mt-1 flex-shrink-0" />
              </div>
            </button>
          ))}
          {displayDocs.length === 0 && (
            <div className="px-4 py-12 text-center text-gray-400 text-sm">
              {search ? "No documents match your search." : "No documents found."}
            </div>
          )}
        </div>
      </div>

      {/* Right: Selected document detail + viewer */}
      {selectedDoc ? (
        <div className="flex-1 flex flex-col bg-gray-100">
          {/* Doc info bar */}
          <div className="flex items-center justify-between px-4 py-2 bg-white border-b">
            <div className="flex items-center gap-2 min-w-0">
              <DocumentTextIcon className="w-4 h-4 text-green-600 flex-shrink-0" />
              <span className="text-sm font-medium text-gray-900 truncate">{selectedDoc.filename}</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => { setChatDoc(selectedDoc); setShowChat(true); }}
                className="p-1.5 text-gray-400 hover:text-purple-600 rounded hover:bg-gray-100"
                title="Chat about this document"
              >
                <ChatBubbleLeftRightIcon className="w-4 h-4" />
              </button>
              {viewerUrl && (
                <a href={viewerUrl} target="_blank" rel="noopener noreferrer"
                  className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100" title="Open">
                  <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                </a>
              )}
              {viewerUrl && (
                <a href={viewerUrl} download={selectedDoc.filename}
                  className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100" title="Download">
                  <ArrowDownTrayIcon className="w-4 h-4" />
                </a>
              )}
              <button
                onClick={() => { if (confirm("Delete?")) deleteMutation.mutate(selectedDoc.id); }}
                className="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-gray-100"
                title="Delete"
              >
                <TrashIcon className="w-4 h-4" />
              </button>
              <button onClick={() => { setSelectedDoc(null); setViewerUrl(null); }}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-100">
                <XMarkIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Split: AI summary on top, document viewer below */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* AI Summary panel */}
            {selectedDoc.notes && (
              <div className="bg-white border-b px-5 py-4">
                <div className="flex items-center gap-2 mb-2">
                  <SparklesIcon className="w-4 h-4 text-green-600" />
                  <h3 className="text-xs font-bold text-green-700 uppercase tracking-wider">AI Summary</h3>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed">{selectedDoc.notes}</p>

                {/* Metadata badges */}
                <div className="flex flex-wrap gap-2 mt-3">
                  {selectedDoc.doc_type && (
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${docTypeColor(selectedDoc.doc_type)}`}>
                      {selectedDoc.doc_type}
                    </span>
                  )}
                  {selectedDoc.category && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-green-50 text-green-700 capitalize">
                      {selectedDoc.category}
                    </span>
                  )}
                  {selectedDoc.fiscal_year && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-600">
                      <CalendarIcon className="w-3 h-3 inline mr-0.5" />FY {selectedDoc.fiscal_year}
                    </span>
                  )}
                  <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">
                    {formatBytes(selectedDoc.file_size)}
                  </span>
                </div>

                {/* AI Tags */}
                {(selectedDoc as any).metadata_?.ai_tags && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {((selectedDoc as any).metadata_.ai_tags as string[]).map((tag, i) => (
                      <span key={i} className="px-1.5 py-0.5 bg-gray-50 text-gray-500 rounded text-[10px] border">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Document viewer */}
            <div className="flex-1 bg-gray-900 overflow-hidden">
              {viewerUrl ? (
                selectedDoc.filename.toLowerCase().endsWith(".pdf") ? (
                  <iframe src={viewerUrl} className="w-full h-full border-0" title={selectedDoc.filename} />
                ) : /\.(png|jpg|jpeg|gif|webp)$/i.test(selectedDoc.filename) ? (
                  <div className="w-full h-full flex items-center justify-center p-8">
                    <img src={viewerUrl} alt={selectedDoc.filename} className="max-w-full max-h-full object-contain" />
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-gray-400">
                    <a href={viewerUrl} target="_blank" rel="noopener noreferrer" className="text-green-400 hover:underline">
                      Open file in new tab
                    </a>
                  </div>
                )
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">Loading...</div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* No doc selected - show overview */
        !selectedDoc && documents && documents.length > 0 && (
          <div className="flex-1 flex items-center justify-center bg-gray-50">
            <div className="text-center text-gray-400">
              <DocumentTextIcon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p className="text-lg font-medium text-gray-500">Select a document</p>
              <p className="text-sm">Click any document on the left to view details and AI summary</p>
            </div>
          </div>
        )
      )}

      {/* Modals */}
      {showUpload && selectedProject && (
        <UploadModal projectId={selectedProject} onClose={() => setShowUpload(false)} />
      )}

      {showChat && chatDoc && (
        <DocumentChatModal document={chatDoc} isOpen={showChat} onClose={() => setShowChat(false)} />
      )}

      {showNewProject && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">Create Project</h2>
            <div className="space-y-4">
              <input type="text" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="Project name" />
              <select value={newProjectType} onChange={(e) => setNewProjectType(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
                <option value="">General</option>
                <option value="town">Town</option>
                <option value="school">School District</option>
              </select>
              <div className="flex justify-end gap-3">
                <button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-gray-600">Cancel</button>
                <button onClick={() => createProjectMutation.mutate()} disabled={!newProjectName}
                  className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">Create</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
