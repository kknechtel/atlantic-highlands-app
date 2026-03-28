"use client";

import {
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  ArrowsPointingOutIcon,
  ArrowsPointingInIcon,
} from "@heroicons/react/24/outline";
import { useState } from "react";

interface Props {
  url: string;
  filename: string;
  onClose: () => void;
}

export default function SplitDocViewer({ url, filename, onClose }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`border-l bg-white flex flex-col transition-all ${
        expanded ? "w-2/3" : "w-1/2"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-gray-50">
        <span className="text-sm font-medium text-gray-700 truncate max-w-[60%]">
          {filename}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200"
            title={expanded ? "Shrink" : "Expand"}
          >
            {expanded ? (
              <ArrowsPointingInIcon className="w-4 h-4" />
            ) : (
              <ArrowsPointingOutIcon className="w-4 h-4" />
            )}
          </button>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200"
            title="Open in new tab"
          >
            <ArrowTopRightOnSquareIcon className="w-4 h-4" />
          </a>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded hover:bg-gray-200"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Document */}
      <div className="flex-1 overflow-hidden">
        {filename.toLowerCase().endsWith(".pdf") ? (
          <iframe src={url} className="w-full h-full border-0" title={filename} />
        ) : /\.(png|jpg|jpeg|gif|webp)$/i.test(filename) ? (
          <div className="w-full h-full flex items-center justify-center bg-gray-100 p-4">
            <img
              src={url}
              alt={filename}
              className="max-w-full max-h-full object-contain"
            />
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              Open file in new tab
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
