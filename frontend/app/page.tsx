import { PageShell } from "@/components/layout/page-shell";
import { QueryDashboard } from "@/components/query/query-dashboard";

export default function HomePage() {
  return (
    <PageShell>
      <QueryDashboard />
    </PageShell>
  );
}
