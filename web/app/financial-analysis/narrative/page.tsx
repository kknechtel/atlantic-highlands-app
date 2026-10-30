import { redirect } from "next/navigation";

// The year-over-year narrative now lives on the main Finances page; this
// route stays so old links and bookmarks still land somewhere useful.
export default function NarrativePage() {
  redirect("/financial-analysis");
}
