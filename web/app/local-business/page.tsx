"use client";

import { useState, useMemo, useEffect } from "react";
import {
  MapPinIcon,
  StarIcon,
  MagnifyingGlassIcon,
  GlobeAltIcon,
  ClockIcon,
  PhoneIcon,
  MusicalNoteIcon,
  DocumentTextIcon,
} from "@heroicons/react/24/outline";
import { StarIcon as StarSolidIcon } from "@heroicons/react/24/solid";

const brandColor = "#385854";

interface Business {
  name: string;
  category: string;
  subcategory?: string;
  address: string;
  rating: number;
  total_reviews: number;
  price_range?: string;
  hours_note?: string;
  description?: string;
  phone?: string;
  website?: string;
  facebook?: string;
  menu_url?: string;
  features?: string[];
  music_schedule?: string;
  instagram?: string;
  social?: { instagram?: string; followers?: number };
  source: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  restaurant: "Restaurants",
  bar: "Bars & Nightlife",
  cafe: "Cafes & Coffee",
  bakery: "Bakeries",
  store: "Retail & Shopping",
  salon: "Salons & Spas",
  gym: "Fitness",
  service: "Services",
};

const CATEGORY_COLORS: Record<string, string> = {
  restaurant: "bg-orange-50 text-orange-700",
  bar: "bg-purple-50 text-purple-700",
  cafe: "bg-amber-50 text-amber-700",
  bakery: "bg-pink-50 text-pink-700",
  store: "bg-blue-50 text-blue-700",
  salon: "bg-rose-50 text-rose-700",
  gym: "bg-green-50 text-green-700",
  service: "bg-gray-100 text-gray-700",
};

function Stars({ rating }: { rating: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        i <= Math.floor(rating)
          ? <StarSolidIcon key={i} className="w-3.5 h-3.5 text-amber-400" />
          : i - 0.5 <= rating
            ? <StarSolidIcon key={i} className="w-3.5 h-3.5 text-amber-200" />
            : <StarIcon key={i} className="w-3.5 h-3.5 text-gray-300" />
      ))}
    </div>
  );
}

export default function LocalBusinessPage() {
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [sortBy, setSortBy] = useState<"rating" | "reviews" | "name">("rating");

  useEffect(() => {
    fetch("/data/businesses.json")
      .then((r) => r.json())
      .then(setBusinesses)
      .catch(() => setBusinesses([]));
  }, []);

  const categories = useMemo(() => {
    const cats = new Map<string, number>();
    businesses.forEach((b) => {
      const cat = b.category || "other";
      cats.set(cat, (cats.get(cat) || 0) + 1);
    });
    return cats;
  }, [businesses]);

  const filtered = useMemo(() => {
    let list = businesses;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((b) =>
        b.name.toLowerCase().includes(q) ||
        (b.description || "").toLowerCase().includes(q) ||
        (b.subcategory || "").toLowerCase().includes(q) ||
        (b.address || "").toLowerCase().includes(q)
      );
    }
    if (categoryFilter) {
      list = list.filter((b) => b.category === categoryFilter);
    }
    list = [...list].sort((a, b) => {
      if (sortBy === "rating") return (b.rating || 0) - (a.rating || 0);
      if (sortBy === "reviews") return (b.total_reviews || 0) - (a.total_reviews || 0);
      return a.name.localeCompare(b.name);
    });
    return list;
  }, [businesses, search, categoryFilter, sortBy]);

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Local Businesses</h1>
          <p className="text-sm text-gray-500 mt-1">
            {businesses.length} businesses in Atlantic Highlands
          </p>
        </div>
      </div>

      {/* Category pills */}
      <div className="flex flex-wrap gap-2 mb-4">
        <button
          onClick={() => setCategoryFilter("")}
          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
            !categoryFilter ? "text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
          style={!categoryFilter ? { backgroundColor: brandColor } : {}}
        >
          All ({businesses.length})
        </button>
        {Array.from(categories.entries())
          .sort((a, b) => b[1] - a[1])
          .map(([cat, count]) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(categoryFilter === cat ? "" : cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                categoryFilter === cat ? "text-white" : CATEGORY_COLORS[cat] || "bg-gray-100 text-gray-600"
              }`}
              style={categoryFilter === cat ? { backgroundColor: brandColor } : {}}
            >
              {CATEGORY_LABELS[cat] || cat} ({count})
            </button>
          ))}
      </div>

      {/* Search + Sort */}
      <div className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <MagnifyingGlassIcon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search businesses..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:border-transparent"
            style={{ "--tw-ring-color": brandColor } as React.CSSProperties}
          />
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as any)}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
        >
          <option value="rating">Highest Rated</option>
          <option value="reviews">Most Reviews</option>
          <option value="name">A-Z</option>
        </select>
      </div>

      {/* Business grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((biz, i) => (
          <div
            key={`${biz.name}-${i}`}
            className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 hover:shadow-md transition-shadow"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-gray-900 truncate">{biz.name}</h3>
                {biz.subcategory && (
                  <span className="text-xs text-gray-500">{biz.subcategory}</span>
                )}
              </div>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium flex-shrink-0 ml-2 ${CATEGORY_COLORS[biz.category] || "bg-gray-100 text-gray-600"}`}>
                {biz.category}
              </span>
            </div>

            {/* Rating */}
            <div className="flex items-center gap-2 mb-2">
              <Stars rating={biz.rating} />
              <span className="text-sm font-medium text-gray-900">{biz.rating}</span>
              <span className="text-xs text-gray-400">({(biz.total_reviews || 0).toLocaleString()} reviews)</span>
            </div>

            {/* Description */}
            {biz.description && (
              <p className="text-xs text-gray-600 mb-3 line-clamp-2">{biz.description}</p>
            )}

            {/* Details */}
            <div className="space-y-1.5 text-xs text-gray-500">
              {biz.address && (
                <div className="flex items-center gap-1.5">
                  <MapPinIcon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{biz.address}</span>
                </div>
              )}
              {biz.price_range && (
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-400 font-medium">$</span>
                  <span>{biz.price_range}</span>
                </div>
              )}
              {biz.hours_note && (
                <div className="flex items-center gap-1.5">
                  <ClockIcon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>{biz.hours_note}</span>
                </div>
              )}
            </div>

            {/* Features tags */}
            {biz.features && biz.features.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3">
                {biz.features.map((f, fi) => (
                  <span key={fi} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">{f}</span>
                ))}
              </div>
            )}

            {/* Music schedule */}
            {biz.music_schedule && (
              <div className="mt-2 flex items-center gap-1.5 text-xs" style={{ color: brandColor }}>
                <MusicalNoteIcon className="w-3.5 h-3.5" />
                <span>{biz.music_schedule}</span>
              </div>
            )}

            {/* Links */}
            <div className="mt-3 pt-3 border-t border-gray-100 flex flex-wrap items-center gap-2">
              {biz.website && (
                <a href={biz.website} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs hover:underline" style={{ color: brandColor }}>
                  <GlobeAltIcon className="w-3.5 h-3.5" /> Website
                </a>
              )}
              {biz.facebook && !biz.website && (
                <a href={biz.facebook} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
                  <GlobeAltIcon className="w-3.5 h-3.5" /> Facebook
                </a>
              )}
              {biz.menu_url && (
                <a href={biz.menu_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-orange-600 hover:underline">
                  <DocumentTextIcon className="w-3.5 h-3.5" /> Menu
                </a>
              )}
              {(biz.instagram || biz.social?.instagram) && (
                <a href={`https://instagram.com/${biz.instagram || biz.social?.instagram}`}
                  target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-pink-600 hover:text-pink-700">
                  @{biz.instagram || biz.social?.instagram}
                </a>
              )}
              {biz.phone && (
                <a href={`tel:${biz.phone}`} className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
                  <PhoneIcon className="w-3.5 h-3.5" /> {biz.phone}
                </a>
              )}
              {biz.social?.followers && (
                <span className="text-[10px] text-gray-400">
                  {biz.social.followers.toLocaleString()} followers
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          {search ? "No businesses match your search." : "No businesses found."}
        </div>
      )}
    </div>
  );
}
