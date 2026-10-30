"use client";
import { TOWN } from "@/lib/municipality";

import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getOverview, type OverviewEntity } from "@/lib/api";
import { DocumentList, MeetingList, MoneyGlance, UpcomingList } from "@/components/overview/OverviewParts";
import { AcademicCapIcon, BuildingOfficeIcon } from "@heroicons/react/24/outline";

export default function Dashboard() {
  return (
    <div className="p-4 md:p-8">
      {/* Banner photo with title overlay. The bottom-to-top
          gradient keeps the white text legible against the bright sky. */}
      <div className="relative h-40 md:h-56 rounded-xl overflow-hidden shadow mb-6 md:mb-8">
        <Image
          src="/dashboard-banner.jpg"
          alt={TOWN.banner_alt || TOWN.name}
          fill
          priority
          sizes="(min-width: 768px) 80vw, 100vw"
          // object-bottom keeps the horizon + water in frame on the short
          // banner crop; default (center) showed only sky.
          className="object-cover object-bottom"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/20 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 p-4 md:p-6 text-white">
          <h1 className="text-2xl md:text-3xl font-bold drop-shadow-lg">What&apos;s happening in {TOWN.name}</h1>
          <p className="text-sm md:text-base text-white/90 drop-shadow">
            Recent meetings, upcoming dates and the money picture for the borough and the school district
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <EntityColumn entity="town" />
        <EntityColumn entity="school" />
      </div>
    </div>
  );
}

function EntityColumn({ entity }: { entity: OverviewEntity }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["overview", entity],
    queryFn: () => getOverview(entity),
    // Scraper runs at midnight ET; refetch every 5 min while the dashboard
    // is foregrounded so newly scraped items surface without a hard reload.
    refetchInterval: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
  });
  const Icon = entity === "school" ? AcademicCapIcon : BuildingOfficeIcon;
  const href = `/${entity}`;

  return (
    <div className="bg-white rounded-xl shadow flex flex-col">
      <Link href={href} className="flex items-center gap-2.5 px-4 md:px-6 py-4 border-b border-gray-100 hover:bg-gray-50 rounded-t-xl">
        <Icon className={`w-6 h-6 ${entity === "school" ? "text-orange-500" : "text-blue-500"}`} />
        <h2 className="text-lg font-semibold text-gray-900 flex-1 truncate">
          {data?.label ?? (entity === "school" ? "School District" : TOWN.official_name)}
        </h2>
        <span className="text-xs text-gray-500 flex-shrink-0">Open →</span>
      </Link>
      <div className="p-4 md:p-6 space-y-6 flex-1">
        {isLoading && <p className="text-sm text-gray-400">Loading…</p>}
        {error && <p className="text-sm text-red-600">Could not load: {(error as Error).message}</p>}
        {data && (
          <>
            <MeetingList meetings={data.meetings} limit={2} />
            <UpcomingList events={data.upcoming} limit={4}
              emptyText={entity === "school" ? "No district events in the next six weeks." : "Nothing on the calendar in the next six weeks."} />
            <MoneyGlance fin={data.finances} entity={entity} />
            <DocumentList docs={data.documents} limit={3} />
          </>
        )}
      </div>
    </div>
  );
}
