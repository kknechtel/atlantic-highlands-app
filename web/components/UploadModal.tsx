"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadMultipleDocuments } from "@/lib/api";
import { XMarkIcon, CloudArrowUpIcon, CheckCircleIcon } from "@heroicons/react/24/outline";

interface UploadModalProps {
  projectId: string;
  onClose: () => void;
}

export default function UploadModal({ projectId, onClose }: UploadModalProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [category, setCategory] = useState("");
  const queryClient = useQueryClient();

  const upload = useMutation({
    mutationFn: () => uploadMultipleDocuments(files, projectId, category || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setTimeout(onClose, 1500);
    },
  });

  const onDrop = useCallback((accepted: File[]) => {
    setFiles((prev) => [...prev, ...accepted]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg", ".jpeg"] },
  });

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Upload Documents</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>

        {/* Dropzone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
            isDragActive ? "border-primary-500 bg-primary-50" : "border-gray-300 hover:border-primary-400"
          }`}
        >
          <input {...getInputProps()} />
          <CloudArrowUpIcon className="w-10 h-10 mx-auto text-gray-400 mb-2" />
          <p className="text-sm text-gray-600">Drag & drop files here, or click to select</p>
          <p className="text-xs text-gray-400 mt-1">PDF, PNG, JPG</p>
        </div>

        {/* File list */}
        {files.length > 0 && (
          <ul className="mt-4 space-y-2 max-h-40 overflow-y-auto">
            {files.map((f, i) => (
              <li key={i} className="flex items-center justify-between text-sm bg-gray-50 rounded px-3 py-2">
                <span className="truncate">{f.name}</span>
                <button onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500 ml-2">
                  <XMarkIcon className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* Category */}
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">Select category...</option>
            <option value="town">Town</option>
            <option value="school">School District</option>
            <option value="general">General</option>
          </select>
        </div>

        {/* Upload button */}
        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">
            Cancel
          </button>
          <button
            onClick={() => upload.mutate()}
            disabled={files.length === 0 || upload.isPending}
            className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2"
          >
            {upload.isSuccess ? (
              <>
                <CheckCircleIcon className="w-4 h-4" /> Uploaded!
              </>
            ) : upload.isPending ? (
              "Uploading..."
            ) : (
              `Upload ${files.length} file${files.length !== 1 ? "s" : ""}`
            )}
          </button>
        </div>

        {upload.isError && (
          <p className="mt-2 text-sm text-red-500">{(upload.error as Error).message}</p>
        )}
      </div>
    </div>
  );
}
