"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getAdminStats, getAdminUsers, toggleUserActive } from "@/lib/api";
import { useAuth } from "@/app/contexts/AuthContext";

export default function AdminPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data: stats } = useQuery({ queryKey: ["admin-stats"], queryFn: getAdminStats });
  const { data: users } = useQuery({ queryKey: ["admin-users"], queryFn: getAdminUsers });

  const toggleMutation = useMutation({
    mutationFn: toggleUserActive,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  if (!user?.is_admin) {
    return (
      <div className="p-8">
        <p className="text-gray-500">Admin access required.</p>
      </div>
    );
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        {[
          { label: "Users", value: stats?.total_users },
          { label: "Projects", value: stats?.total_projects },
          { label: "Documents", value: stats?.total_documents },
          { label: "Statements", value: stats?.total_statements },
        ].map((s) => (
          <div key={s.label} className="bg-white rounded-xl shadow p-4">
            <p className="text-2xl font-bold text-gray-900">{s.value ?? "-"}</p>
            <p className="text-sm text-gray-500">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Users */}
      <div className="bg-white rounded-xl shadow overflow-hidden">
        <div className="px-6 py-4 border-b">
          <h2 className="font-semibold text-gray-900">Users</h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Email</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Username</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Name</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Role</th>
              <th className="text-left px-6 py-3 font-medium text-gray-500">Status</th>
              <th className="text-right px-6 py-3 font-medium text-gray-500">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {users?.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-6 py-3">{u.email}</td>
                <td className="px-6 py-3">{u.username}</td>
                <td className="px-6 py-3">{u.full_name || "-"}</td>
                <td className="px-6 py-3">{u.is_admin ? "Admin" : "User"}</td>
                <td className="px-6 py-3">
                  <span
                    className={`px-2 py-0.5 rounded-full text-xs ${
                      u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                    }`}
                  >
                    {u.is_active ? "Active" : "Disabled"}
                  </span>
                </td>
                <td className="px-6 py-3 text-right">
                  <button
                    onClick={() => toggleMutation.mutate(u.id)}
                    className="text-sm text-primary-600 hover:text-primary-700"
                  >
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
