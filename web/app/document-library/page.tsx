"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getProjects,
  getDocuments,
  createProject,
  deleteDocument,
  searchDocuments,
  getSearchFacets,
  type Project,
  type Document,
} from "@/lib/api";
import UploadModal from "@/components/UploadModal";
import DocumentDetailsModal from "@/components/DocumentDetailsModal";
import DocumentViewer from "@/components/DocumentViewer";
import DocumentChatModal from "@/components/DocumentChatModal";
import {
  FolderPlusIcon,
  ArrowUpTrayIcon,
  TrashIcon,
  EyeIcon,
  MagnifyingGlassIcon,
  ChatBubbleLeftRightIcon,
  InformationCircleIcon,
  FunnelIcon,
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

  // Modal states
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [viewerDoc, setViewerDoc] = useState<Document | null>(null);
  const [showViewer, setShowViewer] = useState(false);
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

  // Search results (when searching)
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
    },
  });

  const handleView = (doc: Document) => {
    setViewerDoc(doc);
    setShowViewer(true);
  };

  const handleDetails = (doc: Document) => {
    setSelectedDoc(doc);
    setShowDetails(true);
  };

  const handleChat = (doc: Document) => {
    setChatDoc(doc);
    setShowChat(true);
  };

  // Use search results when searching, otherwise use document list
  const displayDocs = search.length > 1
    ? (searchResults || []).map((sr) => documents?.find((d) => d.id === sr.id)).filter(Boolean) as Document[]
    : documents?.filter(
        (d) =>
          !search ||
          d.filename.toLowerCase().includes(search.toLowerCase())
      ) || [];

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Document Library</h1>
          <p className="text-sm text-gray-500 mt-1">
            {documents?.length || 0} documents
            {selectedProject && projects
              ? ` in ${projects.find((p) => p.id === selectedProject)?.name || "project"}`
              : ""}
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowNewProject(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <FolderPlusIcon className="w-4 h-4" /> New Project
          </button>
          {selectedProject && (
            <button
              onClick={() => setShowUpload(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              <ArrowUpTrayIcon className="w-4 h-4" /> Upload
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 relative">
          <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents..."
            className="w-full pl-10 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={selectedProject || ""}
          onChange={(e) => setSelectedProject(e.target.value || null)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
        >
          <option value="">All Projects</option>
          {projects?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.document_count})
            </option>
          ))}
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
        >
          <option value="">All Categories</option>
          {facets &&
            Object.entries(facets.categories).map(([k, v]) => (
              <option key={k} value={k === "uncategorized" ? "" : k}>
                {k} ({v})
              </option>
            ))}
        </select>
        <select
          value={docTypeFilter}
          onChange={(e) => setDocTypeFilter(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg"
        >
          <option value="">All Types</option>
          {facets &&
            Object.entries(facets.doc_types).map(([k, v]) => (
              <option key={k} value={k === "unclassified" ? "" : k}>
                {k} ({v})
              </option>
            ))}
        </select>
      </div>

      {/* Document table */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Filename</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Type</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Category</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500">FY</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500">Size</th>
              <th className="text-right px-4 py-3 font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {displayDocs.map((doc) => (
              <tr
                key={doc.id}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => handleDetails(doc)}
              >
                <td className="px-4 py-3 font-medium text-gray-900 max-w-[300px] truncate">
                  {doc.filename}
                </td>
                <td className="px-4 py-3 text-gray-500 capitalize">{doc.doc_type || "-"}</td>
                <td className="px-4 py-3 text-gray-500 capitalize">{doc.category || "-"}</td>
                <td className="px-4 py-3 text-gray-500">{doc.fiscal_year || "-"}</td>
                <td className="px-4 py-3 text-gray-500">{formatBytes(doc.file_size)}</td>
                <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="flex justify-end gap-1">
                    <button
                      onClick={() => handleView(doc)}
                      className="p-1.5 text-gray-400 hover:text-primary-600 rounded hover:bg-gray-100"
                      title="View"
                    >
                      <EyeIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleChat(doc)}
                      className="p-1.5 text-gray-400 hover:text-purple-600 rounded hover:bg-gray-100"
                      title="Chat"
                    >
                      <ChatBubbleLeftRightIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDetails(doc)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-gray-100"
                      title="Details"
                    >
                      <InformationCircleIcon className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm("Delete?")) deleteMutation.mutate(doc.id);
                      }}
                      className="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-gray-100"
                      title="Delete"
                    >
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {displayDocs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                  {search ? "No documents match your search." : "No documents found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Modals */}
      {showUpload && selectedProject && (
        <UploadModal projectId={selectedProject} onClose={() => setShowUpload(false)} />
      )}

      <DocumentDetailsModal
        document={selectedDoc}
        isOpen={showDetails}
        onClose={() => setShowDetails(false)}
        onChat={handleChat}
      />

      <DocumentViewer
        document={viewerDoc}
        isOpen={showViewer}
        onClose={() => setShowViewer(false)}
      />

      <DocumentChatModal
        document={chatDoc}
        isOpen={showChat}
        onClose={() => setShowChat(false)}
      />

      {/* New project modal */}
      {showNewProject && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold mb-4">Create Project</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                <input
                  type="text"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  placeholder="e.g. FY2025 Town Budget"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Entity Type</label>
                <select
                  value={newProjectType}
                  onChange={(e) => setNewProjectType(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="">General</option>
                  <option value="town">Town</option>
                  <option value="school">School District</option>
                </select>
              </div>
              <div className="flex justify-end gap-3">
                <button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-gray-600">
                  Cancel
                </button>
                <button
                  onClick={() => createProjectMutation.mutate()}
                  disabled={!newProjectName || createProjectMutation.isPending}
                  className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
                >
                  Create
                </button>
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
