"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clearAppSetting, getAppSettings, saveAppSetting, type AppSettingView } from "@/lib/api";

const brandColor = "#385854";

function SourceBadge({ s }: { s: AppSettingView }) {
  if (s.source === "app")
    return <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">Saved here</span>;
  if (s.source === "environment")
    return <span className="text-[11px] px-2 py-0.5 rounded bg-gray-100 text-gray-600">From server environment</span>;
  return <span className="text-[11px] px-2 py-0.5 rounded bg-amber-50 text-amber-700">Not set</span>;
}

function SettingRow({ s }: { s: AppSettingView }) {
  const qc = useQueryClient();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const done = () => {
    setValue("");
    setError(null);
    qc.invalidateQueries({ queryKey: ["admin-settings"] });
  };
  const save = useMutation({
    mutationFn: () => saveAppSetting(s.key, value),
    onSuccess: done,
    onError: (e: Error) => setError(e.message),
  });
  const clear = useMutation({
    mutationFn: () => clearAppSetting(s.key),
    onSuccess: done,
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="p-4 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div>
          <p className="font-medium text-gray-900">{s.label}</p>
          <p className="text-xs text-gray-500">{s.help}</p>
        </div>
        <div className="flex items-center gap-2">
          {s.value && <code className="text-xs text-gray-600">{s.value}</code>}
          <SourceBadge s={s} />
        </div>
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) save.mutate();
        }}
      >
        <input
          type={s.secret ? "password" : "text"}
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={s.source ? "Enter a new value to replace it" : "Paste the value"}
          className="flex-1 min-w-0 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={!value.trim() || save.isPending}
          className="px-3 py-1.5 text-sm font-medium rounded-md text-white disabled:opacity-50"
          style={{ backgroundColor: brandColor }}
        >
          Save
        </button>
        {s.source === "app" && (
          <button
            type="button"
            onClick={() => clear.mutate()}
            disabled={clear.isPending}
            className="px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50"
          >
            Remove
          </button>
        )}
      </form>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

export default function AdminSettingsPanel() {
  const { data, isLoading, error } = useQuery({ queryKey: ["admin-settings"], queryFn: getAppSettings });

  return (
    <div className="rounded-xl shadow border border-gray-200 bg-white">
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="font-semibold text-gray-900">API keys</h2>
        <p className="text-xs text-gray-500">
          Saved values are encrypted and take effect within 30 seconds, no restart needed. A value
          saved here overrides the server environment; Remove falls back to it.
        </p>
      </div>
      {isLoading && <p className="p-4 text-sm text-gray-500">Loading...</p>}
      {error && <p className="p-4 text-sm text-red-600">{(error as Error).message}</p>}
      <div className="divide-y divide-gray-100">
        {data?.settings.map((s) => <SettingRow key={s.key} s={s} />)}
      </div>
    </div>
  );
}
