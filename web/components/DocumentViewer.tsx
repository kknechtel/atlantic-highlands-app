"use client";

import { useState, useEffect } from "react";
import { XMarkIcon, ArrowTopRightOnSquareIcon, ArrowDownTrayIcon } from "@heroicons/react/24/outline";

interface DocumentViewerProps {
  url: string | null;
  filename: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function DocumentViewer({ url, filename, isOpen, onClose }: DocumentViewerProps) {
  if (!isOpen || !url) return null;

  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const isImage = /\.(png|jpg|jpeg|gif|webp)$/i.test(filename);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl w-[90vw] h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gray-50 rounded-t-xl">
          <h3 className="font-medium text-gray-900 truncate max-w-[60%]">{filename}</h3>
          <div className="flex items-center gap-2">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-100"
            >
              <ArrowTopRightOnSquareIcon className="w-4 h-4" /> Open
            </a>
            <a
              href={url}
              download={filename}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 border rounded-lg hover:bg-gray-100"
            >
              <ArrowDownTrayIcon className="w-4 h-4" /> Download
            </a>
            <button
              onClick={onClose}
              className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {isPdf ? (
            <iframe src={url} className="w-full h-full border-0" title={filename} />
          ) : isImage ? (
            <div className="w-full h-full flex items-center justify-center bg-gray-100 p-4">
              <img src={url} alt={filename} className="max-w-full max-h-full object-contain" />
            </div>
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-500">
              <div className="text-center">
                <p className="text-lg mb-2">Preview not available for this file type</p>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:text-primary-700 underline"
                >
                  Open in new tab
                </a>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
