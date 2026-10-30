"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getOverview, type OverviewEntity } from "@/lib/api";
import { fmtDay } from "@/lib/money";
import {
  DocumentList, MeetingList, MoneyGlance, OutcomeChip, Section, UpcomingList,
} from "./OverviewParts";
import { AcademicCapIcon, BuildingOfficeIcon, ScaleIcon } from "@heroicons/react/24/outline";

export default function EntityHub({ entity }: { entity: OverviewEntity }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview", entity],
    queryFn: () => getOverview(entity),
  });
  const Icon = entity === "school" ? AcademicCapIcon : BuildingOfficeIcon;

  return (
    <div className="p-3 md:p-8 max-w-6xl">
      <div className="flex items-start gap-3 mb-6">
        <Icon className={`w-8 h-8 flex-shrink-0 ${entity === "school" ? "text-orange-500" : "text-blue-500"}`} />
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-900">{data?.label ?? (entity === "school" ? "School District" : "Borough")}</h1>
          {data?.about && <p className="text-sm text-gray-600 mt-1 max-w-3xl">{data.about}</p>}
        </div>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
      {error && <p className="text-sm text-red-600">Could not load overview: {(error as Error).message}</p>}

      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-xl shadow p-4 md:p-5">
              <MeetingList meetings={data.meetings} limit={5} detailed />
            </div>
            <div className="bg-white rounded-xl shadow p-4 md:p-5">
              <Section title="Ordinances & resolutions · last 6 months" icon={ScaleIcon}>
                {data.legislation.length === 0 ? (
                  <p className="text-sm text-gray-400">None recorded in summarized meetings.</p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {data.legislation.map((l, i) => (
                      <li key={i} className="py-2 flex gap-3 text-sm">
                        <div className="w-24 flex-shrink-0">
                          <OutcomeChip outcome={l.outcome} />
                          {l.number && <div className="text-[11px] text-gray-500 mt-0.5">{l.number}</div>}
                        </div>
                        <div className="min-w-0">
                          <p className="text-gray-800">{l.description}</p>
                          <Link href={`/meetings/${l.meeting_id}`} className="text-[11px] text-gray-500 hover:text-gray-800">
                            {l.meeting_body} · {fmtDay(l.meeting_date)}
                          </Link>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-[11px] text-gray-400 mt-2">Taken from AI meeting summaries — check the minutes for the official record.</p>
              </Section>
            </div>
          </div>
          <div className="space-y-6">
            <div className="bg-white rounded-xl shadow p-4 md:p-5">
              <MoneyGlance fin={data.finances} entity={entity} />
            </div>
            <div className="bg-white rounded-xl shadow p-4 md:p-5">
              <UpcomingList events={data.upcoming} limit={8} emptyText="Nothing on the calendar in the next six weeks." />
            </div>
            <div className="bg-white rounded-xl shadow p-4 md:p-5">
              <DocumentList docs={data.documents} limit={6} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
