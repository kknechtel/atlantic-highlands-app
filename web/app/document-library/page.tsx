"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getDocuments,
  createProject,
  deleteDocument,
  getDocumentViewUrl,
  searchDocuments,
  getSearchFacets,
  type Document,
} from "@/lib/api";
import UploadModal from "@/components/UploadModal";
import DocumentChatModal from "@/components/DocumentChatModal";
import {
  FolderPlusIcon,
  ArrowUpTrayIcon,
  TrashIcon,
  MagnifyingGlassIcon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  SparklesIcon,
  CalendarIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  ArrowDownTrayIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  BuildingOfficeIcon,
  AcademicCapIcon,
  FolderIcon,
} from "@heroicons/react/24/outline";

const brandColor = "#385854";

interface GroupNode {
  label: string;
  icon?: any;
  docs: Document[];
  children: Map<string, GroupNode>;
}

export default function DocumentLibraryPage() {
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectType, setNewProjectType] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [docTypeFilter, setDocTypeFilter] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [chatDoc, setChatDoc] = useState<Document | null>(null);
  const [showChat, setShowChat] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const { data: documents } = useQuery({
    queryKey: ["documents", categoryFilter, docTypeFilter],
    queryFn: () =>
      getDocuments({
        category: categoryFilter || undefined,
        doc_type: docTypeFilter || undefined,
      }),
  });

  const { data: facets } = useQuery({
    queryKey: ["facets"],
    queryFn: () => getSearchFacets(),
  });

  const { data: searchResults } = useQuery({
    queryKey: ["search", search, categoryFilter, docTypeFilter],
    queryFn: () =>
      searchDocuments(search, {
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

  // Filter documents
  const displayDocs = useMemo(() => {
    let docs = documents || [];
    if (search.length > 1 && searchResults) {
      const ids = new Set(searchResults.map((r) => r.id));
      docs = docs.filter((d) => ids.has(d.id));
    }
    if (yearFilter) {
      docs = docs.filter((d) => d.fiscal_year === yearFilter);
    }
    if (deptFilter) {
      docs = docs.filter((d) => d.department === deptFilter);
    }
    return docs;
  }, [documents, search, searchResults, yearFilter, deptFilter]);

  // Get unique fiscal years for filter
  const availableYears = useMemo(() => {
    const years = new Set<string>();
    (documents || []).forEach((d) => { if (d.fiscal_year) years.add(d.fiscal_year); });
    return Array.from(years).sort().reverse();
  }, [documents]);

  // Get unique departments for filter
  const availableDepts = useMemo(() => {
    const depts = new Set<string>();
    (documents || []).forEach((d) => { if (d.department) depts.add(d.department); });
    return Array.from(depts).sort();
  }, [documents]);

  // Build hierarchy: Entity (town/school/other) > Doc Type > Documents
  const hierarchy = useMemo(() => {
    const root = new Map<string, GroupNode>();

    const entityOrder = ["town", "school", "general"];
    const entityLabels: Record<string, string> = {
      town: "Borough of Atlantic Highlands",
      school: "School District",
      general: "General / Uncategorized",
    };
    const entityIcons: Record<string, any> = {
      town: BuildingOfficeIcon,
      school: AcademicCapIcon,
      general: FolderIcon,
    };

    for (const doc of displayDocs) {
      const entity = doc.category || "general";
      const docType = doc.doc_type || "other";

      if (!root.has(entity)) {
        root.set(entity, {
          label: entityLabels[entity] || entity,
          icon: entityIcons[entity] || FolderIcon,
          docs: [],
          children: new Map(),
        });
      }
      const entityNode = root.get(entity)!;

      if (!entityNode.children.has(docType)) {
        entityNode.children.set(docType, {
          label: formatDocType(docType),
          docs: [],
          children: new Map(),
        });
      }
      entityNode.children.get(docType)!.docs.push(doc);
    }

    // Sort docs within each group by fiscal year desc, then filename
    root.forEach((entityNode) => {
      entityNode.children.forEach((typeNode) => {
        typeNode.docs.sort((a, b) => {
          const ya = a.fiscal_year || "";
          const yb = b.fiscal_year || "";
          if (ya !== yb) return yb.localeCompare(ya);
          return a.filename.localeCompare(b.filename);
        });
      });
    });

    // Return in entity order
    const sorted = new Map<string, GroupNode>();
    for (const key of entityOrder) {
      if (root.has(key)) sorted.set(key, root.get(key)!);
    }
    // Add any remaining
    root.forEach((v, k) => { if (!sorted.has(k)) sorted.set(k, v); });
    return sorted;
  }, [displayDocs]);

  const toggleCollapse = (key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const collapseAll = () => {
    const allKeys = new Set<string>();
    hierarchy.forEach((entityNode, entityKey) => {
      allKeys.add(entityKey);
      entityNode.children.forEach((_, typeKey) => {
        allKeys.add(`${entityKey}:${typeKey}`);
      });
    });
    setCollapsed(allKeys);
  };

  const expandAll = () => {
    setCollapsed(new Set());
  };

  const docTypeColor = (type: string | null) => {
    const colors: Record<string, string> = {
      budget: "bg-emerald-50 text-emerald-700",
      audit: "bg-blue-50 text-blue-700",
      financial_statement: "bg-purple-50 text-purple-700",
      minutes: "bg-amber-50 text-amber-700",
      agenda: "bg-orange-50 text-orange-700",
      ordinance: "bg-red-50 text-red-700",
      resolution: "bg-indigo-50 text-indigo-700",
      legal: "bg-pink-50 text-pink-700",
    };
    return colors[type || ""] || "bg-gray-100 text-gray-600";
  };

  const isSearching = search.length > 1;

  return (
    <div className="flex h-full">
      {/* Left: Document list (hidden on mobile when doc selected) */}
      <div className={`${selectedDoc ? "hidden md:flex w-[420px]" : "flex-1"} flex flex-col border-r border-gray-200 bg-white transition-all min-w-0`}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 bg-gray-50 flex-shrink-0">
          <div className="flex items-center justify-between mb-2">
            <h1 className="text-lg font-semibold text-gray-900">Documents</h1>
            <div className="flex gap-1">
              <button onClick={collapseAll}
                className="px-2 py-1 text-[10px] text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200" title="Collapse all">
                Collapse
              </button>
              <button onClick={expandAll}
                className="px-2 py-1 text-[10px] text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200" title="Expand all">
                Expand
              </button>
              <button onClick={() => setShowUpload(true)}
                className="p-1.5 rounded-md hover:opacity-80 text-white" style={{ backgroundColor: brandColor }} title="Upload">
                <ArrowUpTrayIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-2">
            <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search document content..."
              className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:border-transparent bg-white"
              style={{ "--tw-ring-color": brandColor } as React.CSSProperties} />
          </div>

          {/* Filters */}
          <div className="grid grid-cols-2 md:grid-cols-2 gap-1.5 mb-1">
            <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}
              className="px-1.5 py-1 border border-gray-300 rounded text-[11px] bg-white min-w-0">
              <option value="">All Entities</option>
              <option value="town">Town</option>
              <option value="school">School</option>
            </select>
            <select value={docTypeFilter} onChange={(e) => setDocTypeFilter(e.target.value)}
              className="px-1.5 py-1 border border-gray-300 rounded text-[11px] bg-white min-w-0">
              <option value="">All Types</option>
              {facets && Object.keys(facets.doc_types).sort().map((k) => (
                <option key={k} value={k === "unclassified" ? "" : k}>{k}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            <select value={yearFilter} onChange={(e) => setYearFilter(e.target.value)}
              className="px-1.5 py-1 border border-gray-300 rounded text-[11px] bg-white min-w-0">
              <option value="">All Years</option>
              {availableYears.map((y) => <option key={y} value={y}>FY {y}</option>)}
            </select>
            <select value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)}
              className="px-1.5 py-1 border border-gray-300 rounded text-[11px] bg-white min-w-0">
              <option value="">All Departments</option>
              {availableDepts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
          <div className="text-[11px] text-gray-400 mt-1">{displayDocs.length} documents</div>
        </div>

        {/* Document hierarchy */}
        <div className="flex-1 overflow-y-auto">
          {isSearching ? (
            // Flat list for search results
            displayDocs.map((doc) => (
              <DocRow key={doc.id} doc={doc} isSelected={selectedDoc?.id === doc.id}
                onClick={() => handleSelectDoc(doc)} docTypeColor={docTypeColor} />
            ))
          ) : (
            // Hierarchical view
            Array.from(hierarchy.entries()).map(([entityKey, entityNode]) => {
              const entityCollapsed = collapsed.has(entityKey);
              const entityDocCount = Array.from(entityNode.children.values()).reduce((s, n) => s + n.docs.length, 0);
              const EntityIcon = entityNode.icon || FolderIcon;

              return (
                <div key={entityKey}>
                  {/* Entity header */}
                  <button onClick={() => toggleCollapse(entityKey)}
                    className="w-full flex items-center gap-2 px-4 py-2.5 bg-gray-50 border-b border-gray-200 hover:bg-gray-100 transition-colors">
                    {entityCollapsed ? <ChevronRightIcon className="w-3.5 h-3.5 text-gray-400" /> : <ChevronDownIcon className="w-3.5 h-3.5 text-gray-400" />}
                    <EntityIcon className="w-4 h-4" style={{ color: brandColor }} />
                    <span className="text-sm font-semibold text-gray-900 flex-1 text-left">{entityNode.label}</span>
                    <span className="text-[11px] text-gray-400">{entityDocCount}</span>
                  </button>

                  {!entityCollapsed && Array.from(entityNode.children.entries()).map(([typeKey, typeNode]) => {
                    const typeCollapsedKey = `${entityKey}:${typeKey}`;
                    const typeCollapsed = collapsed.has(typeCollapsedKey);

                    return (
                      <div key={typeKey}>
                        {/* Doc type header */}
                        <button onClick={() => toggleCollapse(typeCollapsedKey)}
                          className="w-full flex items-center gap-2 pl-8 pr-4 py-2 border-b border-gray-100 hover:bg-gray-50 transition-colors">
                          {typeCollapsed ? <ChevronRightIcon className="w-3 h-3 text-gray-400" /> : <ChevronDownIcon className="w-3 h-3 text-gray-400" />}
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${docTypeColor(typeKey)}`}>{typeNode.label}</span>
                          <span className="text-[11px] text-gray-400 ml-auto">{typeNode.docs.length}</span>
                        </button>

                        {!typeCollapsed && typeNode.docs.map((doc) => (
                          <DocRow key={doc.id} doc={doc} isSelected={selectedDoc?.id === doc.id}
                            onClick={() => handleSelectDoc(doc)} docTypeColor={docTypeColor} indent />
                        ))}
                      </div>
                    );
                  })}
                </div>
              );
            })
          )}
          {displayDocs.length === 0 && (
            <div className="px-4 py-12 text-center text-gray-400 text-sm">
              {search ? "No documents match your search." : "No documents found."}
            </div>
          )}
        </div>
      </div>

      {/* Right: Selected document detail + viewer */}
      {selectedDoc ? (
        <div className="flex-1 flex flex-col bg-gray-50">
          {/* Doc info bar */}
          <div className="flex items-center justify-between px-3 md:px-4 py-2 bg-white border-b border-gray-200">
            <div className="flex items-center gap-2 min-w-0">
              {/* Mobile back button */}
              <button onClick={() => { setSelectedDoc(null); setViewerUrl(null); }}
                className="md:hidden p-1 text-gray-400 hover:text-gray-600 rounded-md">
                <ChevronLeftIcon className="w-5 h-5" />
              </button>
              <DocumentTextIcon className="w-4 h-4 flex-shrink-0" style={{ color: brandColor }} />
              <span className="text-sm font-medium text-gray-900 truncate">{selectedDoc.filename}</span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <button onClick={() => { setChatDoc(selectedDoc); setShowChat(true); }}
                className="p-1.5 text-gray-400 hover:text-purple-600 rounded-md hover:bg-gray-100" title="Chat">
                <ChatBubbleLeftRightIcon className="w-4 h-4" />
              </button>
              {viewerUrl && (
                <a href={viewerUrl} target="_blank" rel="noopener noreferrer"
                  className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100" title="Open">
                  <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                </a>
              )}
              {viewerUrl && (
                <a href={viewerUrl} download={selectedDoc.filename}
                  className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100" title="Download">
                  <ArrowDownTrayIcon className="w-4 h-4" />
                </a>
              )}
              <button onClick={() => { if (confirm("Delete?")) deleteMutation.mutate(selectedDoc.id); }}
                className="p-1.5 text-gray-400 hover:text-red-500 rounded-md hover:bg-gray-100" title="Delete">
                <TrashIcon className="w-4 h-4" />
              </button>
              <button onClick={() => { setSelectedDoc(null); setViewerUrl(null); }}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
                <XMarkIcon className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 flex flex-col overflow-hidden">
            {/* AI Summary */}
            {selectedDoc.notes && (
              <div className="bg-white border-b border-gray-200 px-5 py-4">
                <div className="flex items-center gap-2 mb-2">
                  <SparklesIcon className="w-4 h-4" style={{ color: brandColor }} />
                  <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: brandColor }}>AI Summary</h3>
                </div>
                <p className="text-sm text-gray-700 leading-relaxed">{selectedDoc.notes}</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {selectedDoc.doc_type && (
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${docTypeColor(selectedDoc.doc_type)}`}>
                      {selectedDoc.doc_type}
                    </span>
                  )}
                  {selectedDoc.category && (
                    <span className="px-2 py-0.5 rounded-full text-xs capitalize" style={{ backgroundColor: `${brandColor}10`, color: brandColor }}>
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
                  {selectedDoc.department && (
                    <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 text-gray-500">
                      {selectedDoc.department}
                    </span>
                  )}
                </div>
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
                    <a href={viewerUrl} target="_blank" rel="noopener noreferrer" className="hover:underline" style={{ color: `${brandColor}cc` }}>
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
        documents && documents.length > 0 && (
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
      {showUpload && (
        <UploadModal projectId="default" onClose={() => setShowUpload(false)} />
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
                <button onClick={() => setShowNewProject(false)} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Cancel</button>
                <button onClick={() => createProjectMutation.mutate()} disabled={!newProjectName}
                  className="px-4 py-2 text-sm text-white rounded-lg hover:opacity-90 disabled:opacity-50"
                  style={{ backgroundColor: brandColor }}>Create</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DocRow({ doc, isSelected, onClick, docTypeColor, indent }: {
  doc: Document; isSelected: boolean; onClick: () => void;
  docTypeColor: (t: string | null) => string; indent?: boolean;
}) {
  return (
    <button onClick={onClick}
      className={`w-full text-left ${indent ? "pl-12" : "pl-4"} pr-4 py-2.5 border-b border-gray-100 hover:bg-gray-50 transition-colors ${
        isSelected ? "border-l-4 bg-gray-50" : ""
      }`}
      style={isSelected ? { borderLeftColor: brandColor, backgroundColor: `${brandColor}08` } : {}}>
      <div className="flex items-center gap-2 min-w-0">
        <DocumentTextIcon className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-gray-900 truncate">{doc.filename}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {doc.fiscal_year && <span className="text-[10px] text-gray-400">FY {doc.fiscal_year}</span>}
            {doc.department && <span className="text-[10px] text-gray-400">{doc.department}</span>}
          </div>
        </div>
        <ChevronRightIcon className="w-3 h-3 text-gray-300 flex-shrink-0" />
      </div>
    </button>
  );
}

function formatDocType(type: string): string {
  const labels: Record<string, string> = {
    budget: "Budgets",
    audit: "Audit Reports",
    financial_statement: "Financial Statements",
    minutes: "Meeting Minutes",
    agenda: "Agendas",
    ordinance: "Ordinances",
    resolution: "Resolutions",
    legal: "Legal Documents",
    other: "Other Documents",
  };
  return labels[type] || type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, " ");
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
